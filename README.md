# Flight Control Interface

A professional flight simulator control interface developed by Ion-Tech LLC. This software allows you to use custom hardware throttle quadrants and control panels with popular flight simulators.

![Main Interface](docs/images/main_interface.png)

## Features

- Support for multiple flight simulators:
  - Microsoft Flight Simulator
  - DCS World
  - X-Plane
  - IL-2 Sturmovik
  - War Thunder
- Dual controller support (Xbox controller or vJoy)
- Real-time axis calibration
- Toggle switch support
- Customizable control mapping
- Modern, dark/light theme interface
- Automatic COM port detection

## Hardware Options

### Option 1: Arduino Mega Setup

#### Components Needed
- Arduino Mega 2560
- 10kΩ potentiometers (for axes)
- Momentary switches/buttons
- Toggle switches
- 10kΩ pull-down resistors for switches
- Project box/enclosure
- USB cable
- 22-24 AWG wire
- Breadboard or PCB

#### Wiring Diagram
![Arduino Mega Wiring](docs/images/mega_wiring.png)

#### Arduino Setup
1. Download and install Arduino IDE
2. Install required libraries:
   ```bash
   # Using Arduino Library Manager
   - "Joystick.h"
   ```
3. Upload the following code:

```cpp:arduino/throttle_controller.ino
#include <Joystick.h>

// Define pins
const int THROTTLE_PIN = A0;
const int PROP_PIN = A1;
const int MIXTURE_PIN = A2;
// Add more pins as needed

void setup() {
  // Initialize analog pins
  pinMode(THROTTLE_PIN, INPUT);
  pinMode(PROP_PIN, INPUT);
  pinMode(MIXTURE_PIN, INPUT);
  
  // Initialize serial communication
  Serial.begin(115200);
}

void loop() {
  // Read analog values
  int throttle = analogRead(THROTTLE_PIN);
  int prop = analogRead(PROP_PIN);
  int mixture = analogRead(MIXTURE_PIN);
  
  // Send data over serial
  Serial.print(throttle);
  Serial.print(",");
  Serial.print(prop);
  Serial.print(",");
  Serial.println(mixture);
  
  delay(10); // Small delay to prevent flooding
}
```

### Option 2: ESP32 Setup

#### Components Needed
- ESP32 DevKit
- Same components as Arduino setup
- Optional: OLED display for status

#### Wiring Diagram
![ESP32 Wiring](docs/images/esp32_wiring.png)

#### ESP32 Setup
1. Install ESP32 board support in Arduino IDE
2. Required libraries:
   ```bash
   # Using Arduino Library Manager
   - "ESP32AnalogRead"
   - "Adafruit SSD1306" (if using OLED)
   ```
3. Upload the following code:

```cpp:esp32/throttle_controller.ino
#include <ESP32AnalogRead.h>

// Define pins - adjust based on your ESP32 board
const int THROTTLE_PIN = 36; // VP
const int PROP_PIN = 39;     // VN
const int MIXTURE_PIN = 34;

// Create analog readers
ESP32AnalogRead throttleReader;
ESP32AnalogRead propReader;
ESP32AnalogRead mixReader;

void setup() {
  // Initialize analog readers with 12-bit resolution
  throttleReader.attach(THROTTLE_PIN);
  propReader.attach(PROP_PIN);
  mixReader.attach(MIXTURE_PIN);
  
  // Initialize serial communication
  Serial.begin(115200);
}

void loop() {
  // Read analog values with averaging
  int throttle = throttleReader.readMiliVolts() / 3.22; // Convert to 0-1023 range
  int prop = propReader.readMiliVolts() / 3.22;
  int mixture = mixReader.readMiliVolts() / 3.22;
  
  // Send data over serial
  Serial.print(throttle);
  Serial.print(",");
  Serial.print(prop);
  Serial.print(",");
  Serial.println(mixture);
  
  delay(10);
}
```

## Software Installation

### Prerequisites

1. Install Python 3.8 or newer from [python.org](https://python.org)

2. Install vJoy from [vJoy Official Site](http://vjoystick.sourceforge.net/site/)
   - Run the vJoy installer
   - Configure a vJoy device with:
     - 8 axes (X, Y, Z, Rx, Ry, Rz, Slider, Dial)
     - 32 buttons
     - POV hats as needed

3. Install required Python packages:
```bash
pip install -r requirements.txt
```

### Software Setup

1. Clone or download this repository
2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Create required directories:
```bash
mkdir -p settings docs/images
```

4. Configure your hardware:
   - Connect your Arduino/ESP32 device
   - Note the COM port number
   - For Windows: Check Device Manager under "Ports (COM & LPT)"
   - For Linux: Look for /dev/ttyUSB* or /dev/ttyACM*
   - For Mac: Look for /dev/cu.usbserial*

### First-Time Configuration

1. Launch the application:
```bash
python flight_stick_reader.py
```

2. The application will automatically detect available COM ports
3. Select your device from the dropdown
4. Click "Connect" to establish communication

## Calibration Process

### Axis Calibration
1. Move each control to its minimum position
2. Click "Set Min" for that control
3. Move to maximum position
4. Click "Set Max"
5. For throttle quadrants with reverse thrust:
   - Set idle position first
   - Then set max forward and max reverse positions

### Control Panel Setup
1. For each potentiometer/switch:
   - Select the control type (Axis/Switch/Button)
   - For axes: Assign to a vJoy axis
   - For buttons: Assign a button number
   - Set threshold values for switches
   - Calibrate min/max positions
   - Test using the built-in tools

## Game-Specific Setup

### Microsoft Flight Simulator
1. Select "MSFS" profile
2. In MSFS controls:
   - Map throttle to Right Trigger
   - Map prop to Right Stick Y
   - Map mixture to Left Stick Y

[Add similar sections for other simulators...]

## Advanced Features

### Toggle Switch Configuration
1. Set control type to "Switch"
2. Assign a button number
3. Set threshold point
4. The switch will toggle state when crossing threshold

### Using as Speedbrake/Spoilers
1. Enable "Use Prop as Speedbrake" option
2. Calibrate range of motion
3. Map in simulator as spoiler axis

## Troubleshooting

### Common Issues

1. COM Port Not Detected
   - Check USB connection
   - Verify in Device Manager
   - Click "Refresh" in the application

2. Controls Not Responding
   - Verify COM port selection
   - Check calibration settings
   - Ensure correct profile is selected

3. vJoy Issues
   - Verify vJoy is installed correctly
   - Check vJoy configuration
   - Restart application after vJoy changes

### Hardware Issues
1. Erratic Readings
   - Check wiring connections
   - Verify ground connections
   - Add/check pull-down resistors
   - Try different USB ports

2. Axis Jitter
   - Increase averaging in Arduino/ESP32 code
   - Check for loose connections
   - Verify power supply stability

## Support Development

This software is provided free of charge by Ion-Tech LLC. If you find it useful, please consider supporting development:

- CashApp: $iontechlimited
- [GitHub Sponsors](#)
- [Buy Me a Coffee](#)

## License & Credits

- Software: Ion-Tech LLC
- Hardware Designs: Open Source
- Documentation: CC BY-SA 4.0

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Contact & Support

- GitHub Issues: [Create an issue](#)
- Email: support@iontech.com
- Discord: [Join our server](#) # SIMUHATER
