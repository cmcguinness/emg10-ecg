/*
 * Logging proxy for hidapi, used to capture the EMAY ECG HD app's USB HID traffic.
 *
 * Build as a dylib that stands in for the app's bundled hidapi.framework binary.
 * It re-exports the real library (renamed hidapi_real) and overrides the calls the
 * app makes, logging each one as hex to $HIDLOG (default /tmp/hidproxy.log).
 */
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>
#include <wchar.h>

typedef struct hid_device_ hid_device;
struct hid_device_info;

static void *real;
static FILE *logf_;

static void init(void) {
    if (real) return;
    Dl_info info;
    dladdr((void *)init, &info);
    char path[4096];
    snprintf(path, sizeof path, "%s", info.dli_fname);
    char *slash = strrchr(path, '/');
    snprintf(slash + 1, sizeof path - (slash + 1 - path), "hidapi_real");
    real = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    const char *lp = getenv("HIDLOG");
    logf_ = fopen(lp ? lp : "/tmp/hidproxy.log", "a");
    if (logf_) setvbuf(logf_, NULL, _IOLBF, 0);
    if (logf_) fprintf(logf_, "# proxy loaded, real=%p (%s)\n", real, path);
}

static double now(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec / 1e6;
}

static void dump(const char *tag, const unsigned char *d, long n) {
    if (!logf_) return;
    fprintf(logf_, "%.3f %s %ld", now(), tag, n);
    for (long i = 0; i < n; i++) fprintf(logf_, " %02x", d[i]);
    fputc('\n', logf_);
}

#define REAL(name, type) static __typeof__(type) fn; init(); if (!fn) fn = (type)dlsym(real, name)

struct hid_device_info *hid_enumerate(unsigned short vid, unsigned short pid) {
    REAL("hid_enumerate", struct hid_device_info *(*)(unsigned short, unsigned short));
    if (logf_) fprintf(logf_, "%.3f ENUM %04x:%04x\n", now(), vid, pid);
    return fn(vid, pid);
}

void hid_free_enumeration(struct hid_device_info *d) {
    REAL("hid_free_enumeration", void (*)(struct hid_device_info *));
    fn(d);
}

hid_device *hid_open(unsigned short vid, unsigned short pid, const wchar_t *serial) {
    REAL("hid_open", hid_device *(*)(unsigned short, unsigned short, const wchar_t *));
    hid_device *h = fn(vid, pid, serial);
    if (logf_) fprintf(logf_, "%.3f OPEN %04x:%04x -> %p\n", now(), vid, pid, (void *)h);
    return h;
}

int hid_set_nonblocking(hid_device *h, int nb) {
    REAL("hid_set_nonblocking", int (*)(hid_device *, int));
    if (logf_) fprintf(logf_, "%.3f NONBLOCK %d\n", now(), nb);
    return fn(h, nb);
}

int hid_write(hid_device *h, const unsigned char *data, size_t len) {
    REAL("hid_write", int (*)(hid_device *, const unsigned char *, size_t));
    int r = fn(h, data, len);
    dump(r >= 0 ? "W" : "W!", data, (long)len);
    return r;
}

int hid_read(hid_device *h, unsigned char *data, size_t len) {
    REAL("hid_read", int (*)(hid_device *, unsigned char *, size_t));
    int r = fn(h, data, len);
    if (r > 0) dump("R", data, r);
    else if (r < 0 && logf_) fprintf(logf_, "%.3f R! %d\n", now(), r);
    return r;
}

int hid_read_timeout(hid_device *h, unsigned char *data, size_t len, int ms) {
    REAL("hid_read_timeout", int (*)(hid_device *, unsigned char *, size_t, int));
    int r = fn(h, data, len, ms);
    if (r > 0) dump("RT", data, r);
    return r;
}

void hid_close(hid_device *h) {
    REAL("hid_close", void (*)(hid_device *));
    if (logf_) fprintf(logf_, "%.3f CLOSE\n", now());
    fn(h);
}
