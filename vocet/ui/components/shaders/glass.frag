#version 440
// One glass (or card) surface in a single pass (design v4): a rounded-rect SDF, a vertical
// fill gradient, a tint, a top sheen, a soft top-left reflection, a 1 px rim that runs
// top -> mid -> bottom (optionally brighter on the top-left / bottom-right diagonal), and a soft
// drop shadow drawn ONLY outside the shape, so it never greys a translucent surface.
// Output is premultiplied. Colours arrive straight (non-premultiplied) as vec4.
//
// `rect` is the shape in the effect item's own px (the item is larger by the shadow's pad).
// For a slice of a taller box (one history row of a day's card) the rect reaches past the item
// at the top and/or bottom, so there are no corners or edges there; the rim's top and bottom
// runs are in px (spanTop / spanBottom), so slices of one box tile seamlessly.
// Compile (qsb.exe ships in the pyside6-addons wheel): qsb --qt6 -o glass.frag.qsb glass.frag
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 itemSize;     // the whole effect item, including the pad
    vec4 rect;         // the shape: left, top, right, bottom (px, item coordinates)
    float radius;
    vec4 fillTop;
    vec4 fillBottom;
    vec4 tint;
    vec4 sheen;
    float sheenH;
    vec4 rimTop;
    vec4 rimMid;
    vec4 rimBottom;
    float rimW;
    float spanTop;       // px from the top edge over which rimTop fades into rimMid
    float spanBottom;    // px from the bottom edge over which rimMid fades into rimBottom
    float rimDiag;       // 0..1: how much the diagonal light varies the rim
    vec4 shadowCol;
    float shadowBlur;
    float shadowY;
    vec4 spec;           // a soft reflection in the top-left corner (light from above-left)
    float specR;         // its radius, px
};

float sdRound(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

vec4 pm(vec4 c) { return vec4(c.rgb * c.a, c.a); }
vec4 over(vec4 top, vec4 below) { return top + below * (1.0 - top.a); }

void main() {
    vec2 px = qt_TexCoord0 * itemSize;
    vec2 b = (rect.zw - rect.xy) * 0.5;
    vec2 p = px - (rect.xy + b);
    float r = min(radius, min(b.x, b.y));
    float d = sdRound(p, b, r);
    float aa = max(fwidth(d), 1e-4);
    float inside = clamp(0.5 - d / aa, 0.0, 1.0);
    float yTop = px.y - rect.y;
    float yBottom = rect.w - px.y;
    float y = clamp(yTop / max(2.0 * b.y, 1.0), 0.0, 1.0);

    // body
    vec4 col = pm(mix(fillTop, fillBottom, y));
    col = over(pm(tint), col);
    float sh = 1.0 - smoothstep(0.0, max(sheenH, 1.0), yTop);
    col = over(pm(vec4(sheen.rgb, sheen.a * sh)), col);
    float sr = length((px - rect.xy) * vec2(0.8, 1.25)) / max(specR, 1.0);
    col = over(pm(vec4(spec.rgb, spec.a * (1.0 - smoothstep(0.0, 1.0, sr)))), col);

    // rim: a ring just inside the edge
    float ring = clamp(0.5 - (abs(d + rimW * 0.5) - rimW * 0.5) / aa, 0.0, 1.0);
    vec4 rc = yTop < spanTop ? mix(rimTop, rimMid, yTop / max(spanTop, 1.0))
            : yBottom < spanBottom ? mix(rimBottom, rimMid, yBottom / max(spanBottom, 1.0))
            : rimMid;
    vec2 n = normalize(p / max(b, vec2(1.0)) + vec2(1e-5));
    float diag = abs(dot(n, vec2(-0.7071, -0.7071)));
    rc.a *= mix(1.0, 0.45 + 0.75 * diag, rimDiag);
    col = over(pm(vec4(rc.rgb, clamp(rc.a, 0.0, 1.0) * ring)), col);
    col *= inside;

    // shadow, outside only
    float ds = sdRound(p - vec2(0.0, shadowY), b, r);
    float sigma = max(shadowBlur * 0.5, 0.5);
    float s = exp(-(max(ds, 0.0) * max(ds, 0.0)) / (2.0 * sigma * sigma));
    vec4 shadow = pm(vec4(shadowCol.rgb, shadowCol.a * s * (1.0 - inside)));

    fragColor = over(col, shadow) * qt_Opacity;
}
