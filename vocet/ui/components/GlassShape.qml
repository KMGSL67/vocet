// One glass surface in one GPU pass (design v4 "Calm glass"): fill gradient, tint, top
// sheen, top-left reflection, a 1 px rim lit from above and a soft shadow drawn only outside the
// shape (shaders/glass.frag). Static: nothing in it animates, so an idle window stays at 0 % CPU.
// It fills its parent and grows past it by the shadow's pad on every side.
// Most code uses C.Glass (kind: pane | card | control | ...), which picks the colours from theme.
//   C.GlassShape { radius: 18; cFillTop: theme.cardTop; cFillBottom: theme.cardBottom; ... }
// sliceTop / sliceBottom: this item is one slice of a taller box (a history row in its day's
// card): the box continues past this edge, so there's no corner, rim or shadow there.
import QtQuick

ShaderEffect {
    id: shape
    property real radius: 16
    property color cFillTop: "transparent"
    property color cFillBottom: cFillTop
    property color cTint: "transparent"
    property color cSheen: "transparent"
    property color cSpec: "transparent"
    property color cRimTop: theme.rimTop
    property color cRimMid: theme.rimMid
    property color cRimBottom: theme.rimBottom
    property color cShadow: "transparent"
    property real sheenH: 48
    property real specR: 160
    property real rimW: theme.highContrast ? 1.5 : 1
    property real rimDiag: 0
    property real shadowBlur: 0
    property real shadowY: 0
    property bool sliceTop: false        // the box continues above this item
    property bool sliceBottom: false     // ... and/or below it
    property real rimSpanTop: -1         // px; -1: 35 % of the height (the rim's top light)
    property real rimSpanBottom: -1      // px; -1: 25 % of the height

    readonly property real pad: shadowBlur > 0 || shadowY !== 0 ? Math.ceil(shadowBlur * 1.7 + Math.abs(shadowY) + 2) : 1
    readonly property real padTop: sliceTop ? 0 : pad
    readonly property real padBottom: sliceBottom ? 0 : pad
    readonly property real shapeW: parent ? parent.width : 0
    readonly property real shapeH: parent ? parent.height : 0
    readonly property real far: 4096     // how far a sliced box reaches past this item

    function v(c) { return Qt.vector4d(c.r, c.g, c.b, c.a) }

    x: -pad
    y: -padTop
    width: shapeW + 2 * pad
    height: shapeH + padTop + padBottom
    visible: shapeW > 0 && shapeH > 0

    property vector2d itemSize: Qt.vector2d(width, height)
    property vector4d rect: Qt.vector4d(pad, sliceTop ? -far : padTop, pad + shapeW,
                                        padTop + shapeH + (sliceBottom ? far : 0))
    property vector4d fillTop: v(cFillTop)
    property vector4d fillBottom: v(cFillBottom)
    property vector4d tint: v(cTint)
    property vector4d sheen: v(cSheen)
    property vector4d spec: v(cSpec)
    property vector4d rimTop: v(cRimTop)
    property vector4d rimMid: v(cRimMid)
    property vector4d rimBottom: v(cRimBottom)
    property vector4d shadowCol: v(cShadow)
    property real spanTop: rimSpanTop >= 0 ? rimSpanTop : shapeH * 0.35
    property real spanBottom: rimSpanBottom >= 0 ? rimSpanBottom : shapeH * 0.25
    blending: true
    fragmentShader: "shaders/glass.frag.qsb"
}
