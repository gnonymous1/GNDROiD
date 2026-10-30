#include "perlin_noise.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>

#define SENSOR_HZ 50 // 50Hz sensor polling rate

int main(int argc, char **argv) {
    printf("[*] Starting IndusBridge Synthetic Sensor Daemon (50Hz Human Entropy Simulation)...\n");
    init_perlin();

    double t = 0.0;
    while (1) {
        // Base gravity vector on Z axis (9.81 m/s^2) + subtle micro-movements
        double noise_x = perlin_noise_3d(t * 0.1, 0.0, 0.0) * 0.035;
        double noise_y = perlin_noise_3d(0.0, t * 0.1, 0.0) * 0.035;
        double noise_z = 9.80665 + perlin_noise_3d(0.0, 0.0, t * 0.1) * 0.020;

        // Micro gyro angular velocity (rad/s)
        double gyro_x = perlin_noise_3d(t * 0.2, 1.0, 0.0) * 0.005;
        double gyro_y = perlin_noise_3d(1.0, t * 0.2, 0.0) * 0.005;
        double gyro_z = perlin_noise_3d(0.0, 1.0, t * 0.2) * 0.003;

        // In production: feeds into /dev/input/eventX or Android IIO sensor nodes
        // Simulated output:
        if ((int)t % 50 == 0) {
            printf("[Sensors] Accel: (%.4f, %.4f, %.4f) m/s² | Gyro: (%.5f, %.5f, %.5f) rad/s\n",
                   noise_x, noise_y, noise_z, gyro_x, gyro_y, gyro_z);
        }

        t += 0.02;
        usleep(20000); // 20ms = 50Hz
    }
    return 0;
}
