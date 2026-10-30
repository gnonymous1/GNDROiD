#pragma once

#ifdef __cplusplus
extern "C" {
#endif

void init_perlin(void);
double perlin_noise_3d(double x, double y, double z);

#ifdef __cplusplus
}
#endif
