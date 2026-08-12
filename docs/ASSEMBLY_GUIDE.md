# Physical Assembly Guide — Bench Prototype

Hardware-only instructions. Software flashing is in `BUILD_INSTRUCTIONS.md`.

Use this layout (same as the wireframe):

```text
[A PLANT ZONE]          [B CONTROL ZONE]           [C FLUID ZONE]
ESP32-CAM + plant       ESP32 + relay + 5V bank    Tank + pump + tubing
```

---

## Tools / parts on the table

- ESP32 DevKit
- ESP32-CAM
- USB-TTL programmer
- Relay module
- Breadboard
- Jumper wires
- 5 V power bank / USB power
- Water pump + pump power
- Tubing (~2–3 m)
- Water container
- Optional: LEDs, fuse holder, rocker switch

---

## Assembly Step 1 — Place the zones

On a **dry desk**:

1. **Left:** plant or leaf sample  
2. **Center:** breadboard (electronics)  
3. **Right/front-low:** water container (keep lower than electronics if possible)

Rule: **water never above or on top of the breadboard.**

---

## Assembly Step 2 — Mount ESP32 DevKit on breadboard

1. Press ESP32 DevKit into the breadboard so both pin rows seat firmly.
2. Identify pins you need:
   - **5V** (or VIN, depending on board labeling)
   - **GND**
   - **GPIO26**
3. Leave USB port accessible for laptop cable.

---

## Assembly Step 3 — Wire the relay (logic side)

Relay module pins are usually: **VCC, GND, IN**

| Wire color suggestion | From | To |
|-----------------------|------|----|
| Red | ESP32 **5V** | Relay **VCC** |
| Black | ESP32 **GND** | Relay **GND** |
| Green/Yellow | ESP32 **GPIO26** | Relay **IN** |

Checks:
- Relay LED/power indicator may light when powered.
- Do **not** connect pump wires to VCC/GND/IN.

---

## Assembly Step 4 — Wire the pump through the relay (power side)

Relay screw terminals are usually: **COM, NO, NC**

Use **COM** and **NO** (Normally Open).

### If pump uses a separate DC adapter (bare wires / DC jack)

```text
Pump adapter +  ----->  Relay COM
Relay NO        ----->  Pump +
Pump adapter -  ----->  Pump -
```

### If pump already has a molded wall plug (AC aquarium style)

Do **not** cut mains wires unless you know electrical safety.  
Prefer a **DC pump** for this student/prototype build.

### Optional safety from your parts kit
- Put **fuse holder + fuse** on the pump **+** line
- Put a **rocker switch** on pump power for manual OFF

---

## Assembly Step 5 — Build the water path

1. Fill container with clean water first (no nutrients yet).
2. Place pump in water **fully submerged** if it is a submersible pump.
3. Attach tubing to pump outlet.
4. Route tubing to:
   - plant tray, or
   - an empty cup (for first leak test)
5. Keep tubing from pulling/tipping the tank onto electronics.
6. Leave slack loop in tubing (drip loop) before electronics area.

```text
[Water tank] ---> [Pump] ---> [Tubing] ---> [Plant tray / test cup]
```

---

## Assembly Step 6 — Power the electronics

### Boards (ESP32 DevKit + later ESP32-CAM)
- Use **5 V power bank** or USB from laptop.

```text
5V Power Bank/USB
   ├─ ESP32 DevKit 5V + GND
   └─ ESP32-CAM 5V + GND   (after CAM is ready)
```

Common **GND** between DevKit and relay is already done in Step 3.

### Pump
- Use pump’s own adapter / wall power through the relay (Step 4).

---

## Assembly Step 7 — Prepare ESP32-CAM mount

1. Place CAM on a small stand/box so lens points at leaves.
2. Distance: about **20–40 cm** from plant.
3. Avoid pointing into harsh direct sun glare.
4. Camera cable/FPC should stay seated flat (don’t twist).

### USB-TTL temporary wiring (for flashing / serial)

| USB-TTL | ESP32-CAM |
|---------|-----------|
| 5V | 5V |
| GND | GND |
| TX | U0R |
| RX | U0T |

For flashing only: add jumper **GPIO0 → GND**, remove after upload.

---

## Assembly Step 8 — Final physical checklist (before coding)

- [ ] DevKit seated on breadboard
- [ ] Relay VCC/GND/IN connected
- [ ] Relay COM/NO connected to pump power path
- [ ] Pump in water, tubing secure, no leaks onto electronics
- [ ] 5V power ready for boards
- [ ] Pump power ready and fused/switched if possible
- [ ] CAM aimed at plant (can flash next)
- [ ] Zones separated: plant / electronics / water

---

## What the finished bench should look like

```text
          (CAM aimed down)
               |
            [Plant]
               
 [Power bank] -- [ESP32 DevKit] -- GPIO26 -- [Relay] -- [Pump PSU]
                                      |                   |
                                   breadboard           [Pump]
                                                          |
                                                       [Tank]
                                                          |
                                                       tubing --> plant tray
```

Wireless later:
```text
ESP32-CAM  ......ESP-NOW......  ESP32 DevKit
```

---

## Next after assembly

Go to **`BUILD_INSTRUCTIONS.md`**:
1. Flash DevKit  
2. Copy MAC  
3. Flash CAM  
4. Test green leaf vs yellow leaf  

If you want, send a photo of your desk wiring and I’ll check it before you power the pump.
