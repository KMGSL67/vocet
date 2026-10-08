// The Vocet glyph: three sound bars in the accent at 70 / 85 / 100 % opacity (80 / 90 /
// 100 in dark, brand.LOGO_OPACITY, so the short bar doesn't turn muddy on black), short
// to tall, flowing into an I-beam caret in textPrimary. Same geometry as brand.paint_glyph:
// bar width = width / 6.45, gaps 0.85 bar, bars 0.34 / 0.54 / 0.76 of the height, the caret
// the full height with serifs 3.2 strokes wide. In mono the bars and caret share one ink, and
// the opacities still separate them.
// While you dictate (backend.listening) and the window is on screen, the bars follow
// backend.micLevel. Hidden or minimised, nothing is bound to the level at all.
//   C.Logo { width: 22; height: 18; wordmark: true }
import QtQuick
import "." as C

Item {
    id: logo
    property bool wordmark: false
    property bool listening: backend.listening
    readonly property bool shown: Window.window !== null && Window.visibility !== Window.Hidden
                                  && Window.visibility !== Window.Minimized
    readonly property bool live: listening && shown
    readonly property real glyphWidth: wordmark ? height * 22 / 18 : width
    readonly property real barW: glyphWidth / 6.45
    readonly property var rest: [0.34, 0.54, 0.76]
    readonly property var alphas: [theme.logoBarA1, theme.logoBarA2, theme.logoBarA3]

    implicitWidth: wordmark ? glyphWidth + 8 + word.implicitWidth : 22
    implicitHeight: 18
    Accessible.role: Accessible.Graphic
    Accessible.name: "Vocet"

    Repeater {
        model: 3
        Rectangle {
            required property int index
            // bound to the level only while live, so a hidden window never re-evaluates this
            readonly property real voice: logo.live ? Math.min(1, backend.micLevel * (1.6 + index * 0.35)) : 0
            width: logo.barW
            radius: width / 2
            x: index * logo.barW * 1.85
            height: Math.max(width, logo.height * Math.min(1, logo.rest[index] + voice * 0.45))
            y: (logo.height - height) / 2
            color: theme.accent  // the full violet; accentText (the lighter text shade) read as pale lavender
            opacity: logo.alphas[index]
            Behavior on height { enabled: logo.live && !backend.reducedMotion; NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        }
    }

    Item {  // the caret (I-beam)
        readonly property real stroke: logo.barW * 0.52
        readonly property real serif: stroke * 3.2
        readonly property real cx: 3 * logo.barW * 1.85 + logo.barW * 0.45
        x: cx - serif / 2
        width: serif
        height: logo.height
        Rectangle { x: (parent.width - width) / 2; width: parent.stroke; height: parent.height; radius: width / 2; color: theme.textPrimary }
        Rectangle { width: parent.width; height: parent.stroke; radius: height / 2; color: theme.textPrimary }
        Rectangle { width: parent.width; height: parent.stroke; radius: height / 2; y: parent.height - height; color: theme.textPrimary }
    }

    Text {
        id: word
        visible: logo.wordmark
        x: logo.glyphWidth + 8
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -0.5
        text: "vocet"
        font.family: "Segoe UI Variable Display Semibold"
        font.pixelSize: 17
        font.weight: Font.DemiBold
        color: theme.textPrimary
        Accessible.ignored: true
    }
}
