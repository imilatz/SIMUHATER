// Handbrake using single potentiometer

const int HANDBRAKE_PIN = A0;
const int SAMPLES = 10;

int readings[SAMPLES];
int readIndex = 0;
int total = 0;

void setup() {
  Serial.begin(115200);
  pinMode(HANDBRAKE_PIN, INPUT);
  
  // Initialize readings array
  for (int i = 0; i < SAMPLES; i++) {
    readings[i] = 0;
  }
}

void loop() {
  // Remove oldest reading
  total = total - readings[readIndex];
  
  // Read new value
  readings[readIndex] = analogRead(HANDBRAKE_PIN);
  
  // Add new reading to total
  total = total + readings[readIndex];
  
  // Advance index
  readIndex = (readIndex + 1) % SAMPLES;
  
  // Calculate average and send
  int smoothedValue = total / SAMPLES;
  Serial.println(smoothedValue);
  
  delay(20);
} 