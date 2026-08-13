/*
 * Capture adapter for the official MPV test3dbpp.c generator.
 *
 * This implements only the public binpack3d callback used by test3dbpp.c.
 * It does not modify the official source and does not solve an instance.
 * Each callback writes the native format documented in readme.3dbpp.
 *
 * GNU C build example:
 *   gcc -ansi -O2 -o mpv_capture test3dbpp.c mpv_capture_adapter.c -lm
 */

#include <stdio.h>
#include <stdlib.h>

void binpack3d(
    int n, int W, int H, int D,
    int *w, int *h, int *d,
    int *x, int *y, int *z, int *bno,
    int *lb, int *ub,
    int nodelimit, int iterlimit, int timelimit,
    int *nodeused, int *iterused, int *timeused,
    int packingtype)
{
    static int instance_number = 0;
    char filename[64];
    FILE *output;
    int i;

    (void)x; (void)y; (void)z; (void)bno;
    (void)nodelimit; (void)iterlimit; (void)timelimit; (void)packingtype;

    instance_number++;
    sprintf(filename, "mpv_instance_%02d.txt", instance_number);
    output = fopen(filename, "w");
    if (output == NULL) {
        fprintf(stderr, "cannot create MPV capture file %s\n", filename);
        exit(EXIT_FAILURE);
    }
    fprintf(output, "%d %d %d %d\n", n, W, H, D);
    for (i = 0; i < n; i++) {
        fprintf(output, "%d %d %d\n", w[i], h[i], d[i]);
    }
    if (fclose(output) != 0) {
        fprintf(stderr, "cannot close MPV capture file %s\n", filename);
        exit(EXIT_FAILURE);
    }

    *lb = 0; *ub = 0;
    *nodeused = 0; *iterused = 0; *timeused = 0;
}
