# Arduino Implementation Guide

## Hardware Requirements

### Components List
- 1x Arduino Mega 2560
- 3x 10kΩ linear potentiometers (for throttle, prop, mixture)
- 7x 10kΩ linear potentiometers (for control panel)
- Toggle/momentary switches (as needed)
- 1x Project enclosure
- 22-24 AWG wire (multiple colors recommended)
- Breadboard or PCB
- USB-A to USB-B cable
- 2.54mm pin headers
- Optional: Panel mount potentiometer bushings

### Tools Needed
- Soldering iron and solder
- Wire strippers
- Small Phillips screwdriver
- Drill with step bit (for enclosure)
- Multimeter
- Hot glue gun (for strain relief)

## Wiring Diagram

```plaintext
                                 Arduino Mega 2560
                                 ┌──────────────┐
                    5V ─────────►│5V            │
                    GND ────────►│GND           │
                                │              │
Throttle Pot ─────────────────►│A0            │
  - Wiper pin → A0             │              │
  - Left pin → GND             │              │
  - Right pin → 5V             │              │
                                │              │
Prop Pot ───────────────────►│A1            │
  - Wiper pin → A1             │              │
  - Left pin → GND             │              │
  - Right pin → 5V             │              │
                                │              │
Mixture Pot ────────────────►│A2            │
  - Wiper pin → A2             │              │
  - Left pin → GND             │              │
  - Right pin → 5V             │              │
                                │              │
Control Panel:                  │              │
Pot 1 ────────────────────►│A3            │
Pot 2 ────────────────────►│A4            │
Pot 3 ────────────────────►│A5            │
Pot 4 ────────────────────►│A6            │
Pot 5 ────────────────────►│A7            │
Pot 6 ────────────────────►│A8            │
Pot 7 ────────────────────►│A9            │
                                └──────────────┘

Note: Each potentiometer connects to:
- Wiper (middle) pin → Analog pin
- Left pin → GND
- Right pin → 5V
```

## Arduino Code

```cpp:arduino/throttle_controller/throttle_controller.ino
#include <MovingAverage.h>

// Pin definitions
const int THROTTLE_PIN = A0;
const int PROP_PIN = A1;
const int MIXTURE_PIN = A2;

// Control panel pins
const int CONTROL_PANEL_PINS[] = {A3, A4, A5, A6, A7, A8, A9};
const int NUM_PANEL_POTS = 7;

// Moving average filters for smoothing
MovingAverage<float> throttleFilter(10);
MovingAverage<float> propFilter(10);
MovingAverage<float> mixtureFilter(10);
MovingAverage<float> panelFilters[7] = {
    MovingAverage<float>(10),
    MovingAverage<float>(10),
    MovingAverage<float>(10),
    MovingAverage<float>(10),
    MovingAverage<float>(10),
    MovingAverage<float>(10),
    MovingAverage<float>(10)
};

void setup() {
    // Initialize serial at 115200 baud
    Serial.begin(115200);
    
    // Configure analog pins with internal pullup disabled
    pinMode(THROTTLE_PIN, INPUT);
    pinMode(PROP_PIN, INPUT);
    pinMode(MIXTURE_PIN, INPUT);
    
    // Configure control panel pins
    for(int i = 0; i < NUM_PANEL_POTS; i++) {
        pinMode(CONTROL_PANEL_PINS[i], INPUT);
    }
}

void loop() {
    // Read and filter main controls
    float throttle = throttleFilter.add(analogRead(THROTTLE_PIN));
    float prop = propFilter.add(analogRead(PROP_PIN));
    float mixture = mixtureFilter.add(analogRead(MIXTURE_PIN));
    
    // Send main controls data
    Serial.print(throttle);
    Serial.print(",");
    Serial.print(prop);
    Serial.print(",");
    Serial.print(mixture);
    
    // Read and send control panel data
    Serial.print(",CTRLPANEL");
    for(int i = 0; i < NUM_PANEL_POTS; i++) {
        float value = panelFilters[i].add(analogRead(CONTROL_PANEL_PINS[i]));
        Serial.print(",");
        Serial.print(value);
    }
    
    Serial.println();
    delay(10); // 100Hz update rate
}
```

## ESP32 Alternative

If using an ESP32 instead of Arduino Mega:

```cpp:esp32/throttle_controller/throttle_controller.ino
#include <ESP32AnalogRead.h>

// Pin definitions - adjust based on your ESP32 board
const int THROTTLE_PIN = 36;  // VP
const int PROP_PIN = 39;      // VN
const int MIXTURE_PIN = 34;

// Control panel pins
const int CONTROL_PANEL_PINS[] = {35, 32, 33, 25, 26, 27, 14};
const int NUM_PANEL_POTS = 7;

// ADC resolution
const int ADC_RESOLUTION = 12;  // 12-bit resolution (0-4095)

void setup() {
    Serial.begin(115200);
    
    // Configure ADC resolution
    analogReadResolution(ADC_RESOLUTION);
    
    // Configure pins
    for(int i = 0; i < NUM_PANEL_POTS; i++) {
        pinMode(CONTROL_PANEL_PINS[i], INPUT);
    }
}

void loop() {
    // Read main controls
    int throttle = analogRead(THROTTLE_PIN);
    int prop = analogRead(PROP_PIN);
    int mixture = analogRead(MIXTURE_PIN);
    
    // Send main controls data
    Serial.print(throttle);
    Serial.print(",");
    Serial.print(prop);
    Serial.print(",");
    Serial.print(mixture);
    
    // Read and send control panel data
    Serial.print(",CTRLPANEL");
    for(int i = 0; i < NUM_PANEL_POTS; i++) {
        int value = analogRead(CONTROL_PANEL_PINS[i]);
        Serial.print(",");
        Serial.print(value);
    }
    
    Serial.println();
    delay(10); // 100Hz update rate
}
```

## Physical Assembly Tips

### Potentiometer Wiring
1. For each potentiometer:
   - Middle (wiper) pin → Arduino analog pin
   - Left pin → GND
   - Right pin → 5V
   - No external resistors needed - using direct connection

### Layout Recommendations
1. Main Controls:
   ```plaintext
   Front view:
   ┌────────────────────┐
   │  ┌─┐   ┌─┐   ┌─┐  │
   │  │T│   │P│   │M│  │
   │  └─┘   └─┘   └─┘  │
   └────────────────────┘
   T = Throttle
   P = Prop
   M = Mixture
   ```

2. Control Panel:
   - Mount panel potentiometers in logical groups
   - Label each potentiometer clearly
   - Use color-coded wires for easy identification
   - Add strain relief to prevent wire damage

### Calibration Process
1. Open the software and go to the calibration tab
2. For each axis:
   - Move to minimum position → Set minimum
   - Move to maximum position → Set maximum
   - Set idle point if needed
3. Test full range of motion
4. Save calibration settings

## Troubleshooting

### Common Issues

1. Erratic Readings
   - Check wiring connections
   - Verify GND and 5V connections
   - Try different analog pins
   - Increase averaging samples in code

2. Dead Spots
   - Check potentiometer quality
   - Verify full range of motion
   - Clean potentiometer if needed

3. Inverted Axis
   - Use software inversion in calibration
   - Check wiring orientation

### Signal Quality Tips
1. Keep wires short when possible
2. Use shielded cable for long runs
3. Separate signal wires from power wires
4. Add ferrite beads for noise reduction 