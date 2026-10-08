// A rounded rectangle whose colour eases to `tint`: hover in 100 ms, hover out
// 150 ms, press instant, release 100 ms. Colour only: no lift, no scale. Under reduced motion
// state changes keep at most a 100 ms fade. Controls use it as their background:
//   C.Fill { tint: pressed ? theme.fillPressed : hovered ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
//            hovered: control.hovered; pressed: control.pressed }
// For "no fill" use the fill colour at alpha 0 (not "transparent"), so the fade stays one hue.
import QtQuick

Rectangle {
    id: fill
    property color tint: "transparent"
    property bool hovered: false
    property bool pressed: false
    property bool animated: true
    property bool _ready: false
    color: "transparent"

    Component.onCompleted: { color = tint; _ready = true }
    onTintChanged: {
        anim.stop()
        let ms = pressed ? 0 : hovered ? theme.motionFast : theme.motionBase
        if (backend.reducedMotion)
            ms = Math.min(ms, theme.motionFast)
        if (!_ready || !animated || ms <= 0 || !visible) {
            color = tint
            return
        }
        anim.to = tint
        anim.duration = ms
        anim.start()
    }
    ColorAnimation { id: anim; target: fill; property: "color"; easing.type: Easing.OutCubic }
}
