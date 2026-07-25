# Camera Mission Tutorial (Payload Selection • Lighting • Image Quality)

Use this guide to set up your balloon’s camera mission so you get usable, sharp images (and not blurry, washed-out, or noisy footage).

---

## 1) Payload selection: pick the “right” camera for the mission

### A. Decide: stills, video, or both
- **Stills-first**: prioritise higher resolution and better stabilization.
- **Video-first**: prioritise frame rate + reliable exposure control (manual is best).
- **Both**: pick a camera that can do 4K/5K still capture (or high-res burst) without overheating.

### B. Match the camera to the expected environment
High-altitude balloon missions typically see:
- **Huge dynamic range**: bright clouds/sky + dark ground.
- **Fast-changing lighting**: sun angle changes quickly during flight.
- **Cold temps (often)**: batteries drain faster; electronics can throttle.

So prefer cameras that support:
- **Manual exposure** (or exposure lock)
- **Low-light performance** (larger sensor or strong optics)
- **Reasonable bitrate/compression control** (especially for video)

### C. Budgeting rules (what usually hurts image quality)
- **Too low resolution** → you can’t recover detail later.
- **Auto-exposure fighting the scene** → flicker between frames.
- **Over-compression (video)** → blocky skies and smeared textures.
- **No stabilization / poor mounting** → shake becomes “motion blur.”

---

## 2) Mounting & placement: keep the horizon steady

### A. Physical stability beats “fancy settings”
Your best settings won’t save you from shake.
- Use a **rigid mount** with short fasteners.
- Add **shock isolation** only if it doesn’t allow wobble.
- Ensure the camera points where you need **before** launch—avoid “tweak at the last second.”

### B. Pointing strategy
- If you want **landscape**: aim for horizon-centred framing.
- If you want **cloud detail**: tilt slightly upward to avoid over-undershooting the sky.
- If you want **terrestrial detail**: pick an angle that avoids straight-on glare.

---

## 3) Lighting conditions: how to anticipate what the camera will “see”

Lighting is the main driver of exposure and contrast.

### A. Clear sky / sun behind clouds (high contrast)
Common issue: sky becomes **too bright**, ground becomes **too dark**.
Fixes:
- Use **manual exposure** (or exposure compensation) rather than relying on auto.
- Prefer **slightly underexposed** capture to preserve highlights.

### B. Direct sun (glare and washed highlights)
Common issue: specular glare on clouds; blown whites.
Fixes:
- Use a **lens hood** or shade the lens if possible.
- Avoid aiming directly at the sun.

### C. Overcast / haze (low contrast)
Common issue: everything looks **flat**.
Fixes:
- Slightly higher exposure (within highlight limits).
- Consider a bit more sharpening later (or a higher-contrast profile) if your pipeline supports it.

### D. Golden hour / sunset (beautiful, but tricky)
Common issue: increased noise + long shadows.
Fixes:
- Increase exposure carefully; use noise reduction that doesn’t smear edges.
- If you must use high ISO, keep it consistent (don’t let auto jump).

---

## 4) Camera settings that matter most

### A. Exposure (aperture/shutter/ISO)
- **Manual exposure** is the #1 quality multiplier for missions.
- Lock exposure to prevent frame-to-frame flicker.
- In video, aim for:
  - **Shutter speed** that matches your motion (avoid extremely slow shutter).
  - **ISO** as low as practical for the desired shutter speed.

### B. Focus
- Prefer **manual focus** or focus lock.
- Ensure your minimum focus distance matches expected targets.
- For landscapes at distance: focus near infinity (but verify on test footage).

### C. Resolution & frame rate
- Stills: capture the **highest native resolution**.
- Video: use the highest quality mode you can store reliably.

### D. White balance
- Prefer a **fixed white balance** instead of auto.
- Auto WB can “hunt” when clouds pass.

### E. File formats (especially for post-production)
- If your workflow allows it: capture in the **highest bit-depth / least lossy** mode available.

---

## 5) Image quality checks (before launch)

Run a quick “quality preflight”:
1. **Record 10–30 seconds** in the expected lighting direction.
2. Inspect on the device or immediately pull frames:
   - Is the horizon sharp?
   - Are highlights blown (pure white areas with no detail)?
   - Does exposure stay consistent across the clip?
   - Is there obvious motion blur?
3. Adjust one variable at a time (usually exposure first).

---

## 6) In-mission best practices (what to watch)

### A. Battery & thermal constraints
- Cold can reduce battery capacity and cause throttling.
- If your setup allows it, use a **battery plan** that survives the cold portion.

### B. Storage planning
- Ensure the camera can record continuously for the entire mission window.
- High-res video fills storage quickly—underestimating storage is a common failure.

### C. Protect the lens
- Clean the lens with appropriate materials.
- If your environment can fog/condense: use lens protection strategy (e.g., desiccant system or approved anti-fog approach).

---

## 7) Common failure modes & quick fixes

1. **Overexposed sky / blown clouds**
   - Fix: manual exposure; underexpose slightly; avoid pointing at the sun.

2. **Black ground / low detail**
   - Fix: raise exposure carefully; consider capturing with consistent settings that preserve highlight headroom.

3. **Blurry / shaky footage**
   - Fix: improve mount rigidity; adjust stabilization approach; shorten shutter for video or use higher FPS if supported.

4. **Flickering brightness across frames**
   - Fix: lock exposure + white balance; avoid auto modes.

5. **Noise / grainy images**
   - Fix: reduce ISO when possible; ensure proper exposure; apply sensible post-processing.

---

## 8) Quick mission checklist

Before launch:
- [ ] Camera set to **manual** (or locked) exposure + WB
- [ ] Focus locked for expected scene distance
- [ ] Rigid mount; no wobble
- [ ] Storage + battery verified for the full mission duration
- [ ] Lens clean; lens protected from fog/condensation
- [ ] 10–30s test clip checked for sharpness + highlight detail

---

If you want, tell me what camera/payload options your game currently exposes (e.g., “1080p vs 4K”, “auto vs manual”, “stills vs video”), and I’ll tailor this tutorial to match your exact in-game UI and constraints.
