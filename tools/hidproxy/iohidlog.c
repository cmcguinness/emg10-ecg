/*
 * DYLD_INSERT_LIBRARIES shim that logs IOKit HID traffic, used to capture how the
 * Contec "Portable ECG Monitor" app talks to the EMAY EMG-10 (Contec PM10).
 *
 * Interposes the IOHIDDevice report calls and wraps input-report callbacks.
 * Logs to stderr (the app is sandboxed, so files outside its container are off-limits).
 */
#include <IOKit/hid/IOHIDDevice.h>
#include <stdio.h>
#include <sys/time.h>

#define DYLD_INTERPOSE(_replacement, _replacee)                                   \
    __attribute__((used)) static struct {                                         \
        const void *replacement;                                                  \
        const void *replacee;                                                     \
    } _interpose_##_replacee __attribute__((section("__DATA,__interpose"))) = {  \
        (const void *)(unsigned long)&_replacement, (const void *)(unsigned long)&_replacee};

static double now(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec / 1e6;
}

static void dump(const char *tag, IOHIDReportType type, uint32_t id, const uint8_t *d, CFIndex n) {
    fprintf(stderr, "HIDLOG %.3f %s t%d id%u %ld", now(), tag, (int)type, id, (long)n);
    for (CFIndex i = 0; i < n; i++) fprintf(stderr, " %02x", d[i]);
    fputc('\n', stderr);
}

static IOReturn my_SetReport(IOHIDDeviceRef dev, IOHIDReportType type, CFIndex id,
                             const uint8_t *report, CFIndex len) {
    IOReturn r = IOHIDDeviceSetReport(dev, type, id, report, len);
    dump(r == kIOReturnSuccess ? "W" : "W!", type, (uint32_t)id, report, len);
    return r;
}
DYLD_INTERPOSE(my_SetReport, IOHIDDeviceSetReport)

static IOReturn my_SetReportWithCallback(IOHIDDeviceRef dev, IOHIDReportType type, CFIndex id,
                                         const uint8_t *report, CFIndex len, CFTimeInterval timeout,
                                         IOHIDReportCallback cb, void *ctx) {
    dump("WCB", type, (uint32_t)id, report, len);
    return IOHIDDeviceSetReportWithCallback(dev, type, id, report, len, timeout, cb, ctx);
}
DYLD_INTERPOSE(my_SetReportWithCallback, IOHIDDeviceSetReportWithCallback)

static IOReturn my_GetReport(IOHIDDeviceRef dev, IOHIDReportType type, CFIndex id,
                             uint8_t *report, CFIndex *len) {
    IOReturn r = IOHIDDeviceGetReport(dev, type, id, report, len);
    if (r == kIOReturnSuccess) dump("GET", type, (uint32_t)id, report, *len);
    return r;
}
DYLD_INTERPOSE(my_GetReport, IOHIDDeviceGetReport)

/* Input reports: wrap the app's callback so every report is logged before delivery. */
#define MAX_CB 8
static struct { IOHIDReportCallback cb; void *ctx; } cbs[MAX_CB];
static int ncb;

static void wrapped(void *slot, IOReturn result, void *sender, IOHIDReportType type,
                    uint32_t id, uint8_t *report, CFIndex len) {
    int i = (int)(long)slot;
    dump("R", type, id, report, len);
    cbs[i].cb(cbs[i].ctx, result, sender, type, id, report, len);
}

static void my_RegisterInput(IOHIDDeviceRef dev, uint8_t *report, CFIndex len,
                             IOHIDReportCallback cb, void *ctx) {
    fprintf(stderr, "HIDLOG %.3f REGISTER_INPUT len %ld\n", now(), (long)len);
    if (!cb || ncb >= MAX_CB) {
        IOHIDDeviceRegisterInputReportCallback(dev, report, len, cb, ctx);
        return;
    }
    int i = ncb++;
    cbs[i].cb = cb;
    cbs[i].ctx = ctx;
    IOHIDDeviceRegisterInputReportCallback(dev, report, len, wrapped, (void *)(long)i);
}
DYLD_INTERPOSE(my_RegisterInput, IOHIDDeviceRegisterInputReportCallback)

__attribute__((constructor)) static void hello(void) {
    fprintf(stderr, "HIDLOG %.3f shim loaded\n", now());
}
