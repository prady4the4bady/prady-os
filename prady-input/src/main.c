#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <linux/uinput.h>
#include <systemd/sd-bus.h>
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>

#define UINPUT_DEV "/dev/uinput"

int uinput_fd = -1;

/* Initialize uinput virtual device */
int init_uinput() {
    struct uinput_user_dev uidev;
    
    uinput_fd = open(UINPUT_DEV, O_WRONLY | O_NONBLOCK);
    if (uinput_fd < 0) {
        perror("Failed to open uinput");
        return -1;
    }

    // Enable key and relative mouse events
    ioctl(uinput_fd, UI_SET_EVBIT, EV_KEY);
    ioctl(uinput_fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(uinput_fd, UI_SET_KEYBIT, BTN_RIGHT);
    
    ioctl(uinput_fd, UI_SET_EVBIT, EV_REL);
    ioctl(uinput_fd, UI_SET_RELBIT, REL_X);
    ioctl(uinput_fd, UI_SET_RELBIT, REL_Y);

    memset(&uidev, 0, sizeof(uidev));
    snprintf(uidev.name, UINPUT_MAX_NAME_SIZE, "Kryos Virtual AI Controller");
    uidev.id.bustype = BUS_USB;
    uidev.id.vendor  = 0x1234;
    uidev.id.product = 0x5678;
    uidev.id.version = 1;

    if (write(uinput_fd, &uidev, sizeof(uidev)) < 0) {
        perror("Failed to write to uinput");
        return -1;
    }

    if (ioctl(uinput_fd, UI_DEV_CREATE) < 0) {
        perror("Failed to create uinput device");
        return -1;
    }

    return 0;
}

/* D-Bus method: MoveMouse(x, y) */
static int method_move_mouse(sd_bus_message *m, void *userdata, sd_bus_error *ret_error) {
    int x, y;
    int r;

    r = sd_bus_message_read(m, "ii", &x, &y);
    if (r < 0) return r;

    printf("AI requested mouse move to: (%d, %d)\n", x, y);

    // If X11 is available, we can use XTest for absolute positioning as fallback.
    // For pure uinput, we would inject REL_X/REL_Y or configure ABS_X/ABS_Y.
    Display *dpy = XOpenDisplay(NULL);
    if (dpy) {
        XTestFakeMotionEvent(dpy, -1, x, y, CurrentTime);
        XFlush(dpy);
        XCloseDisplay(dpy);
    } else {
        printf("Wayland fallback not fully implemented in this minimal C stub\n");
    }

    return sd_bus_reply_method_return(m, "b", 1);
}

/* D-Bus vtable for org.kryos.Input */
static const sd_bus_vtable kryos_vtable[] = {
    SD_BUS_VTABLE_START(0),
    SD_BUS_METHOD("MoveMouse", "ii", "b", method_move_mouse, SD_BUS_VTABLE_UNPRIVILEGED),
    SD_BUS_VTABLE_END
};

int main(int argc, char *argv[]) {
    sd_bus_slot *slot = NULL;
    sd_bus *bus = NULL;
    int r;

    printf("Starting kryos-input daemon...\n");

    if (init_uinput() < 0) {
        fprintf(stderr, "Warning: Running without uinput kernel support\n");
    }

    r = sd_bus_open_user(&bus);
    if (r < 0) {
        fprintf(stderr, "Failed to connect to user bus: %s\n", strerror(-r));
        goto finish;
    }

    r = sd_bus_add_object_vtable(bus,
                                 &slot,
                                 "/org/kryos/Input",
                                 "org.kryos.Input",
                                 kryos_vtable,
                                 NULL);
    if (r < 0) {
        fprintf(stderr, "Failed to issue method call: %s\n", strerror(-r));
        goto finish;
    }

    r = sd_bus_request_name(bus, "org.kryos.Input", 0);
    if (r < 0) {
        fprintf(stderr, "Failed to acquire service name: %s\n", strerror(-r));
        goto finish;
    }

    printf("Listening on D-Bus (org.kryos.Input)\n");

    for (;;) {
        r = sd_bus_process(bus, NULL);
        if (r < 0) {
            fprintf(stderr, "Failed to process bus: %s\n", strerror(-r));
            goto finish;
        }
        if (r > 0) continue;

        r = sd_bus_wait(bus, (uint64_t) -1);
        if (r < 0) {
            fprintf(stderr, "Failed to wait on bus: %s\n", strerror(-r));
            goto finish;
        }
    }

finish:
    sd_bus_slot_unref(slot);
    sd_bus_unref(bus);
    if (uinput_fd >= 0) {
        ioctl(uinput_fd, UI_DEV_DESTROY);
        close(uinput_fd);
    }
    return r < 0 ? EXIT_FAILURE : EXIT_SUCCESS;
}
