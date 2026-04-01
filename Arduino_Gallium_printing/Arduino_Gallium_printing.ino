const int CONTACT_PIN = 2;
const int LED_PIN     = 13;
volatile bool contactDetected = false;
bool latchSent = false;

void onContact() {
    contactDetected = true;
}

void setup() {
    Serial.begin(115200);
    pinMode(LED_PIN, OUTPUT);
    digitalWrite(LED_PIN, LOW);
    pinMode(CONTACT_PIN, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(CONTACT_PIN), onContact, FALLING);
    Serial.println("READY");
}

void loop() {
    if (contactDetected && !latchSent) {
        latchSent = true;
        digitalWrite(LED_PIN, HIGH);
        Serial.println("CONTACT");
    }

    if (Serial.available() > 0) {
        char cmd = Serial.read();
        if (cmd == 'r') {
            detachInterrupt(digitalPinToInterrupt(CONTACT_PIN));
            contactDetected = false;
            latchSent = false;
            digitalWrite(LED_PIN, LOW);
            delay(50);
            attachInterrupt(digitalPinToInterrupt(CONTACT_PIN), onContact, FALLING);
            Serial.println("READY");
        }
    }
}