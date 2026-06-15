# Dexhand-ble (fork of original)
The DexHand is an anthropomorphic robot hand that we have selected as a reference / starting point for a bachelor's thesis in mechatronics engineering (University of Brasilia, 2026).

![make-a-gif_AdobeExpress-2](https://github.com/iotdesignshop/dexhand-ble/assets/2821763/de311dc5-b41e-4f2f-b8e6-849a51983018)

Arduino-based firmware, and a Python-based hand tracking demo to demonstrate the V1.0 DexHand - a low-cost, open-source, 3D printed humanoid robot hand.

*Note: This project covers the software and firmware for basic control of a V1.0 DexHand. If you'd like to learn more about how to build your own hand, you can visit our page explaining this process at (https://www.dexhand.org). It has a lot more information on the hardware and physical build of this low-cost, open source dexterous hand.*



# Attribution
The original DexHand project and mechanical designs were created by [The Robot Studio](http://www.therobotstudio.com) and released in the [V1.0-Dexhand project on GitHub](https://github.com/TheRobotStudio/V1.0-Dexhand). This project draws upon that mechanical design, adding software and firmware function to the original work. The original project was released under the Creative Commons "Attribution-NonCommercial-ShareAlike 4.0 International" License (or CC BY-NC-SA 4.0) and as such this project is released with the same license to comply with those terms.

We would like to thank The Robot Studio for releasing such an interesting and inspiring design to Open Source and we are happy to support that effort with this repo which will hopefully augment the original project in useful ways with software, firmware, and some additional assembly instructions.

# Software Project Overview

## Project Contents 
This project consists of two subfolders:
- **Arduino** Contains Arduino-based Firmware to install on an [Arduino Nano RP2040 Connect](https://docs.arduino.cc/hardware/nano-rp2040-connect) board to control the servos inside the DexHand, and to provide a Bluetooth Low Energy (BLE) connection to the hand controls for wirelessly streaming data to the hand.
- **Python** Contains a Python demo script that uses [Google MediaPipe Hand Tracker](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker) to generate poses for the hand based on a webcam feed, sending those poses over the BLE connection to the Arduino board
