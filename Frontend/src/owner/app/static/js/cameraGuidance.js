// Image-based capture guidance for the phone camera.
//
// Checks the part of the live preview inside the on-screen guide for texture
// scale, framing, sharpness, lighting, glare and stability. It does NOT measure
// physical distance, and GREEN only means the capture conditions are acceptable;
// the CNN still decides the textile class.
//
// The scale / sharpness / brightness values are measured on the same 224x224
// view the CNN uses. Defaults come from the training photos; recalibrate with
//   python "Backend/machine learning/calibrate_camera_guidance.py"
// and with the on-phone Calibration Mode (open classify.html?calibrate=1).
const CAMERA_GUIDANCE_CONFIG = {
    // Set to false to remove Calibration Mode (?calibrate=1) completely.
    CALIBRATION_MODE_ALLOWED: true,

    ANALYSIS_INTERVAL_MS: 200,
    // Must match calibrate_camera_guidance.py.
    ANALYSIS_SIZE: 224,
    GRID_CELLS: 4,
    GLARE_LEVEL: 250,
    MOTION_THUMB_SIZE: 28,

    // Guide rectangle, as width / height. Training photos are 3:4 / 4:3.
    GUIDE_ASPECT: 3 / 4,
    // Send only the guide region to the CNN. Training photos were entirely
    // textile, so the guide region (textile only) matches them better than the
    // full frame, which also contains background. See MOBILE_CAMERA_GUIDANCE.md.
    CROP_TO_GUIDE: true,

    // Zoom applied when the camera opens (clamped to what the device supports).
    INITIAL_ZOOM: 1,
    MAX_REQUESTED_ZOOM: 10,

    // Framing: is there textile everywhere inside the guide?
    TEXTURE_MIN: 5,
    COVERAGE_CELL_ABS_MIN: 4,
    COVERAGE_CELL_RELATIVE: 0.45,
    COVERAGE_GOOD_MIN: 0.75,
    COVERAGE_ADJUST_MIN: 0.5,

    // Texture scale (0..1): smaller = texture looks smaller (too far),
    // larger = texture looks bigger (too close). Training photos: p1 0.461,
    // p5 0.474, median 0.546, p95 0.664, p99 0.715 (jusi ~0.49, pina ~0.55,
    // cocoon ~0.65). The same photos simulated 2x farther read ~0.35,
    // 1.4x farther ~0.45, 1.4x closer ~0.67, 2x closer ~0.79, 3x closer ~0.82-0.91.
    // The band is set closer than the training photos on purpose.
    SCALE_ADJUST_MIN: 0.45,
    SCALE_GOOD_MIN: 0.53,
    SCALE_GOOD_MAX: 0.88,
    SCALE_ADJUST_MAX: 0.95,

    // Laplacian variance on the 224x224 view. Training photos: cocoon p1 86,
    // jusi/pina p1 > 890. Live video is softer than still photos.
    SHARPNESS_MIN: 20,
    SHARPNESS_GOOD_MIN: 40,

    // Mean brightness 0..255. Training photos: 168 - 179.
    BRIGHTNESS_DARK: 60,
    BRIGHTNESS_DIM: 90,
    BRIGHTNESS_BRIGHT: 225,
    BRIGHTNESS_TOO_BRIGHT: 245,

    // Fraction of near-white pixels. Advisory only; never blocks capture.
    GLARE_WARN: 0.02,

    // Frame-to-frame change of a 28x28 thumbnail, divided by texture strength so
    // fine and coarse fabrics compare. On training photos a 0.1% shift between
    // frames reads ~0.01-0.03, but on close-up fabric any shift of 1% or more
    // reads ~0.5-0.8 (the same as panning across the fabric), while pointing
    // away from the fabric reads 2-33. So this only catches large movements;
    // blur from hand shake is caught by the sharpness check instead.
    MOTION_STABLE_MAX: 1.0,
    MOTION_HIGH: 2.0,
    MOTION_SMOOTHING_FRAMES: 5,
    STABLE_HOLD_MS: 200
};

function createCameraGuidance(config) {
    const size = config.ANALYSIS_SIZE;
    const gradSize = size - 1;
    const half = size / 2;
    const thumbSize = config.MOTION_THUMB_SIZE;
    const block = size / thumbSize;
    const cellCount = config.GRID_CELLS * config.GRID_CELLS;

    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const context = canvas.getContext("2d", { willReadFrequently: true });

    // Halving in steps keeps the 224x224 view consistent whether the source is a
    // 1000 px video region or a 4000 px photo; a single large drawImage aliases.
    const scratch = [document.createElement("canvas"), document.createElement("canvas")];

    const luma = new Float32Array(size * size);
    const grad = new Float32Array(gradSize * gradSize);
    const halfLuma = new Float32Array(half * half);
    const cells = new Float32Array(cellCount);
    const sortedCells = new Float32Array(cellCount);
    let thumb = new Float32Array(thumbSize * thumbSize);
    let previousThumb = new Float32Array(thumbSize * thumbSize);
    let hasPreviousThumb = false;
    let stableSince = null;
    let recentMotion = [];

    function reset() {
        hasPreviousThumb = false;
        stableSince = null;
        recentMotion = [];
    }

    // Median of the last few readings, so a single jumpy frame (autofocus,
    // exposure change, small tremor) does not break "stable".
    function smoothedMotion(motion) {
        if (motion === null) {
            return null;
        }
        recentMotion.push(motion);
        if (recentMotion.length > config.MOTION_SMOOTHING_FRAMES) {
            recentMotion.shift();
        }
        const sorted = recentMotion.slice().sort(function (a, b) {
            return a - b;
        });
        return sorted[Math.floor((sorted.length - 1) / 2)];
    }

    function drawRegion(source, region) {
        let from = source;
        let sx = region.x;
        let sy = region.y;
        let sw = region.width;
        let sh = region.height;
        let step = 0;

        while (sw > 2 * size || sh > 2 * size) {
            const width = Math.max(size, Math.round(sw / 2));
            const height = Math.max(size, Math.round(sh / 2));
            const target = scratch[step % 2];

            if (target.width !== width) {
                target.width = width;
            }
            if (target.height !== height) {
                target.height = height;
            }

            const targetContext = target.getContext("2d");
            targetContext.imageSmoothingEnabled = true;
            targetContext.imageSmoothingQuality = "high";
            targetContext.drawImage(from, sx, sy, sw, sh, 0, 0, width, height);

            from = target;
            sx = 0;
            sy = 0;
            sw = width;
            sh = height;
            step++;
        }

        context.imageSmoothingEnabled = true;
        context.imageSmoothingQuality = "high";
        context.drawImage(from, sx, sy, sw, sh, 0, 0, size, size);
    }

    function analyze(video, region) {
        drawRegion(video, region);

        const pixels = context.getImageData(0, 0, size, size).data;

        let brightnessSum = 0;
        let glareCount = 0;

        for (let i = 0, p = 0; i < luma.length; i++, p += 4) {
            const y =
                0.299 * pixels[p] + 0.587 * pixels[p + 1] + 0.114 * pixels[p + 2];
            luma[i] = y;
            brightnessSum += y;
            if (y >= config.GLARE_LEVEL) {
                glareCount++;
            }
        }

        let gradSum = 0;
        for (let y = 0; y < gradSize; y++) {
            const row = y * size;
            for (let x = 0; x < gradSize; x++) {
                const center = luma[row + x];
                const value =
                    Math.abs(luma[row + x + 1] - center) +
                    Math.abs(luma[row + size + x] - center);
                grad[y * gradSize + x] = value;
                gradSum += value;
            }
        }
        const texture = gradSum / (gradSize * gradSize);

        for (let j = 0; j < half; j++) {
            for (let i = 0; i < half; i++) {
                const top = 2 * j * size + 2 * i;
                halfLuma[j * half + i] =
                    (luma[top] + luma[top + 1] +
                        luma[top + size] + luma[top + size + 1]) / 4;
            }
        }

        let coarseSum = 0;
        for (let y = 0; y < half - 1; y++) {
            const row = y * half;
            for (let x = 0; x < half - 1; x++) {
                const center = halfLuma[row + x];
                coarseSum +=
                    Math.abs(halfLuma[row + x + 1] - center) +
                    Math.abs(halfLuma[row + half + x] - center);
            }
        }
        const coarse = coarseSum / ((half - 1) * (half - 1));
        const scale = texture > 1e-6 ? coarse / (2 * texture) : 0;

        let lapSum = 0;
        let lapSquares = 0;
        for (let y = 1; y < size - 1; y++) {
            const row = y * size;
            for (let x = 1; x < size - 1; x++) {
                const i = row + x;
                const lap =
                    4 * luma[i] - luma[i - size] - luma[i + size] -
                    luma[i - 1] - luma[i + 1];
                lapSum += lap;
                lapSquares += lap * lap;
            }
        }
        const lapCount = (size - 2) * (size - 2);
        const lapMean = lapSum / lapCount;
        const sharpness = lapSquares / lapCount - lapMean * lapMean;

        const grid = config.GRID_CELLS;
        for (let row = 0; row < grid; row++) {
            const y0 = Math.floor(row * gradSize / grid);
            const y1 = Math.floor((row + 1) * gradSize / grid);
            for (let col = 0; col < grid; col++) {
                const x0 = Math.floor(col * gradSize / grid);
                const x1 = Math.floor((col + 1) * gradSize / grid);
                let sum = 0;
                for (let y = y0; y < y1; y++) {
                    for (let x = x0; x < x1; x++) {
                        sum += grad[y * gradSize + x];
                    }
                }
                cells[row * grid + col] = sum / ((y1 - y0) * (x1 - x0));
            }
        }
        sortedCells.set(cells);
        sortedCells.sort();
        const reference = sortedCells[Math.floor(0.75 * (cellCount - 1))];
        const cellThreshold = Math.max(
            config.COVERAGE_CELL_ABS_MIN,
            config.COVERAGE_CELL_RELATIVE * reference
        );
        let coveredCells = 0;
        for (let i = 0; i < cellCount; i++) {
            if (cells[i] >= cellThreshold) {
                coveredCells++;
            }
        }

        for (let ty = 0; ty < thumbSize; ty++) {
            for (let tx = 0; tx < thumbSize; tx++) {
                let sum = 0;
                for (let y = ty * block; y < (ty + 1) * block; y++) {
                    for (let x = tx * block; x < (tx + 1) * block; x++) {
                        sum += luma[y * size + x];
                    }
                }
                thumb[ty * thumbSize + tx] = sum / (block * block);
            }
        }
        let motion = null;
        if (hasPreviousThumb) {
            let diff = 0;
            for (let i = 0; i < thumb.length; i++) {
                diff += Math.abs(thumb[i] - previousThumb[i]);
            }
            motion = diff / thumb.length / Math.max(texture, 1);
        }
        const swap = previousThumb;
        previousThumb = thumb;
        thumb = swap;
        hasPreviousThumb = true;

        return {
            brightness: brightnessSum / luma.length,
            glare: glareCount / luma.length,
            texture: texture,
            scale: scale,
            sharpness: sharpness,
            coverage: coveredCells / cellCount,
            motion: motion
        };
    }

    function check(state, message) {
        return { state: state, message: message };
    }

    function distanceCheck(m) {
        if (m.texture < config.TEXTURE_MIN) {
            return check("bad", "Point at the textile and hold steady");
        }
        if (m.coverage < config.COVERAGE_ADJUST_MIN || m.scale < config.SCALE_ADJUST_MIN) {
            return check("bad", "Move closer");
        }
        if (m.scale > config.SCALE_ADJUST_MAX) {
            return check("bad", "Move slightly farther");
        }
        if (m.coverage < config.COVERAGE_GOOD_MIN || m.scale < config.SCALE_GOOD_MIN) {
            return check("adjust", "Adjust distance — slightly closer");
        }
        if (m.scale > config.SCALE_GOOD_MAX) {
            return check("adjust", "Adjust distance — slightly farther");
        }
        return check("good", "Good distance");
    }

    function focusCheck(m) {
        if (m.sharpness < config.SHARPNESS_MIN) {
            return check("bad", "Image blurry — hold steady");
        }
        if (m.sharpness < config.SHARPNESS_GOOD_MIN) {
            return check("adjust", "Image slightly soft — hold steady");
        }
        return check("good", "Focus OK");
    }

    function lightingCheck(m) {
        if (m.brightness < config.BRIGHTNESS_DARK) {
            return check("bad", "Too dark — improve lighting");
        }
        if (m.brightness > config.BRIGHTNESS_TOO_BRIGHT) {
            return check("bad", "Too bright — reduce glare");
        }
        if (m.brightness < config.BRIGHTNESS_DIM) {
            return check("adjust", "Lighting is dim — add light");
        }
        if (m.brightness > config.BRIGHTNESS_BRIGHT) {
            return check("adjust", "Very bright — reduce light");
        }
        return check("good", "Lighting OK");
    }

    function glareCheck(m) {
        return m.glare > config.GLARE_WARN
            ? check("adjust", "Reduce glare / change angle")
            : check("good", "No strong glare");
    }

    function stabilityCheck(m, now) {
        const motion = smoothedMotion(m.motion);
        if (motion === null || motion > config.MOTION_HIGH) {
            stableSince = null;
            return check("bad", "Hold steady");
        }
        if (motion > config.MOTION_STABLE_MAX) {
            stableSince = null;
            return check("adjust", "Hold steady");
        }
        if (stableSince === null) {
            stableSince = now;
        }
        if (now - stableSince < config.STABLE_HOLD_MS) {
            return check("adjust", "Hold steady…");
        }
        return check("good", "Stable");
    }

    function evaluate(m, now) {
        const checks = {
            distance: distanceCheck(m),
            lighting: lightingCheck(m),
            focus: focusCheck(m),
            stability: stabilityCheck(m, now),
            glare: glareCheck(m)
        };

        // Blur also inflates the scale reading, so a blurry frame is reported as
        // blurry rather than "too close" - unless there is no textile detail at all.
        const noTextile = m.texture < config.TEXTURE_MIN;
        const blockingOrder = noTextile
            ? ["lighting", "distance", "focus", "stability"]
            : ["lighting", "focus", "distance", "stability"];
        const adjustOrder = ["distance", "lighting", "focus", "stability"];

        const firstBad = blockingOrder.find(function (name) {
            return checks[name].state === "bad";
        });
        const firstAdjust = adjustOrder.find(function (name) {
            return checks[name].state === "adjust";
        });

        let level = "green";
        let headline = "Click this to Capture";

        if (firstBad) {
            level = "red";
            headline = checks[firstBad].message;
        } else if (firstAdjust) {
            level = "yellow";
            headline = checks[firstAdjust].message;
        }

        return {
            level: level,
            headline: headline,
            checks: checks,
            canCapture: level === "green"
        };
    }

    return { analyze: analyze, evaluate: evaluate, reset: reset };
}
