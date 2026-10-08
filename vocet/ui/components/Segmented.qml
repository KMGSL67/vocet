// A segmented control (design v4): text only, nouns, at most 5 segments, never for switching
// views (Language: Automatic · English · Deutsch). A 34 px glass groove (capsule); equal
// segments (widest label + 28 px, or `fillWidth` shared out: wider stretches them; narrower, the
// last resort so the control never sticks out of its card, shrinks them and elides the labels,
// which screen readers still get whole); the selected segment is a brighter
// glass capsule, inset 3, that glides over 260 ms (instant under reduced motion). Labels callout
// 13 px; selected semibold textPrimary, others textSecondary. A radio group: Tab lands on the current segment, ←/→ change the choice,
// each segment is announced as a radio button.
//   C.Segmented {
//       label: "Language"
//       model: [{ key: "auto", label: "Automatic" }, { key: "en", label: "English" }, { key: "de", label: "Deutsch" }]
//       value: backend.settings.language
//       onPicked: (v) => backend.setSetting("language", v)
//   }
// model can also be a list of strings (then the value is the string).
import QtQuick
import QtQuick.Templates as T
import "." as C

Item {
    id: seg
    property string label: ""
    property var model: []
    property string textRole: "label"
    property string valueRole: "key"
    property var value
    property string demoState: ""      // gallery only: "focus"
    signal picked(var value)

    readonly property int count: model ? model.length : 0
    readonly property int currentIndex: {
        for (let i = 0; i < count; i++)
            if (valueAt(i) === value) return i
        return -1
    }
    readonly property real segmentWidth: fillWidth > 0 ? (fillWidth - 6) / Math.max(1, count) : widest + 28
    readonly property real naturalWidth: count * (widest + 28) + 6   // the width without fillWidth
    readonly property bool anyFocus: demoState === "focus" || focusedIndex >= 0
    property int focusedIndex: -1
    // The thumb glides only when the choice changes (not when the control resizes or first lays out).
    property bool glide: false
    property bool ready: false
    Component.onCompleted: ready = true
    onCurrentIndexChanged: if (ready) { glide = true; glideOff.restart() }
    Timer { id: glideOff; interval: theme.motionGlide + 50; onTriggered: seg.glide = false }
    property real widest: 0
    property real fillWidth: 0         // > 0: the segments share exactly this width (see above)
    readonly property real hairline: 1 / Screen.devicePixelRatio

    function textAt(i) { const m = model[i]; return typeof m === "string" ? m : m[textRole] }
    function valueAt(i) { const m = model[i]; return typeof m === "string" ? m : m[valueRole] }
    function choose(i) {
        if (i < 0 || i >= count) return
        const r = repeater.itemAt(i)
        if (r) r.forceActiveFocus(Qt.TabFocusReason)
        if (i !== currentIndex) picked(valueAt(i))
    }
    function measure() {
        let w = 0
        for (let i = 0; i < measures.count; i++) {
            const t = measures.itemAt(i)
            if (t) w = Math.max(w, t.implicitWidth)
        }
        widest = Math.ceil(w)
    }

    implicitWidth: count * segmentWidth + 6
    implicitHeight: Math.max(34, theme.calloutLine + 16)
    opacity: enabled ? 1 : 0.4
    Accessible.role: Accessible.Grouping
    Accessible.name: label

    Repeater {  // invisible labels, to size every segment to the widest one
        id: measures
        model: seg.count
        C.Txt {
            required property int index
            visible: false
            text: seg.textAt(index)
            textStyle: "callout"
            onImplicitWidthChanged: seg.measure()
        }
        onCountChanged: seg.measure()
    }

    C.Glass {  // the groove
        id: track
        anchors.fill: parent
        kind: "track"
        radius: height / 2
        C.FocusRing { show: seg.anyFocus; controlRadius: seg.height / 2 }
    }

    Item {  // the selected segment: a brighter glass lens that glides between segments
        id: thumb
        visible: seg.currentIndex >= 0
        x: 3 + Math.max(0, seg.currentIndex) * seg.segmentWidth
        y: 3
        width: seg.segmentWidth
        height: seg.height - 6
        Behavior on x { enabled: seg.glide && !backend.reducedMotion; NumberAnimation { duration: theme.motionGlide; easing.type: Easing.OutCubic } }
        C.Glass { anchors.fill: parent; kind: "thumb"; radius: height / 2 }
        Rectangle {
            visible: theme.highContrast
            anchors.fill: parent
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: theme.strokeStrong
        }
    }

    Repeater {
        id: repeater
        model: seg.count
        T.AbstractButton {
            id: segment
            required property int index
            readonly property bool current: index === seg.currentIndex
            x: 3 + index * seg.segmentWidth
            y: 3
            width: seg.segmentWidth
            height: seg.height - 6
            leftPadding: 8                 // the label's room when fillWidth squeezes the segments
            rightPadding: 8
            hoverEnabled: true
            focusPolicy: current || (seg.currentIndex < 0 && index === 0) ? Qt.StrongFocus : Qt.ClickFocus
            Accessible.role: Accessible.RadioButton
            Accessible.name: seg.textAt(index)
            Accessible.checkable: true
            Accessible.checked: current
            onClicked: seg.choose(index)
            onVisualFocusChanged: seg.focusedIndex = visualFocus ? index : (seg.focusedIndex === index ? -1 : seg.focusedIndex)
            Keys.onLeftPressed: seg.choose(index - 1)
            Keys.onRightPressed: seg.choose(index + 1)

            background: C.Fill {
                radius: height / 2
                hovered: segment.hovered
                tint: segment.hovered && !segment.current ? theme.fillHover : Qt.alpha(theme.fillHover, 0)
            }
            contentItem: C.Txt {
                text: seg.textAt(segment.index)
                textStyle: "callout"
                tone: segment.current ? "primary" : "secondary"
                semibold: segment.current
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                Accessible.ignored: true
            }
        }
    }
}
