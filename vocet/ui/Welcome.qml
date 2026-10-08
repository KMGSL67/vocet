// The first-run welcome: four short steps in one sheet, shown once, right after the
// opening mark. Short, skippable,
// taught by doing (step 3 is a real dictation), the microphone only opened when you ask to test
// it, and no download without a button press.
//   1 Hello       the shortcut as keycaps (they press once), what Vocet does, two promises
//   2 Your voice  microphone + "Test microphone" (a level meter only while testing),
//                 Languages you speak, and the speech model (ready, or its download)
//   3 Try it      a practice field; a real dictation into it shows a check and "That's it."
//   4 Extras      AI formatting and Start with Windows; "Start using Vocet" finishes
// Skip is always there; Esc skips; closing the window counts as skipped. Either way it's seen
// (backend.finishWelcome) and only Settings › General › Welcome brings it back.
// Keyboard: the sheet holds the focus (Tab cycles Skip → the step → Back → Continue); Main puts
// it back where it was (Show again) or on the page once the welcome has gone.
// Motion: the sheet fades in and rises 8 px (240 ms) once the opening mark is done (`holding`);
// steps cross-fade and slide 8 px in the direction you go (240 ms); the keycaps press once.
// Reduced motion: fades only (100 ms), the keycaps stay still. Nothing loops or runs while idle.
//   Loader { active: backend.welcomeOpen; sourceComponent: Welcome { holding: opening.active } }
import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import "components" as C

FocusScope {
    id: welcome
    objectName: "welcome"
    anchors.fill: parent
    focus: true

    property bool holding: false          // the opening mark is still playing: wait, then enter
    property int step: 0
    readonly property int count: 4
    property bool tried: false            // a dictation arrived in the practice field
    property bool leaving: false
    readonly property bool reduced: backend.reducedMotion
    readonly property int stepMs: reduced ? theme.motionFast : theme.motionPage
    readonly property string keysName: backend.hotkeyName
    readonly property string keysWord: backend.hotkeyIsCombo ? "the keys" : "the key"
    readonly property bool modelReady: (backend.speechModel.state || "ready") === "ready"

    // Scripts (render_window.py) jump straight to a state.
    function jumpTo(n) {
        entrance.stop()
        step = Math.max(0, Math.min(count - 1, n))
        entered = true
        scrim.opacity = 1
        sheet.opacity = 1
        rise.y = 0
    }

    function go(n) {
        if (n < 0 || n >= count || leaving) return
        if (step === 1 && n !== 1) backend.stopMicTest()
        step = n
        Qt.callLater(focusStep)
    }
    function next() { if (step === count - 1) leave(false); else go(step + 1) }
    function back() { go(step - 1) }
    // byKeyboard: Esc, or a button reached with Tab (its focus ring on): Main then gives the focus
    // to the sidebar with its ring, not silently to the page
    signal finishing(bool byKeyboard)
    function leave(skipped, byKeyboard) {
        if (leaving) return
        leaving = true
        backend.stopMicTest()
        const f = welcome.Window.activeFocusItem
        exitAnim.skipped = skipped
        exitAnim.byKeyboard = byKeyboard === true || !!(f && f.visualFocus)
        exitAnim.start()
    }
    function focusStep() {
        if (step === 2 && welcome.modelReady) practice.input.forceActiveFocus(Qt.OtherFocusReason)
        else primary.forceActiveFocus(Qt.OtherFocusReason)
    }

    // ------------------------------------------------------------------ entrance and exit
    property bool entered: false
    function enter() {
        if (entered) return
        entered = true
        rise.y = reduced ? 0 : theme.risePage
        entrance.start()
        Qt.callLater(focusStep)
    }
    onHoldingChanged: if (!holding) enter()
    // Later, not now: on a first run window.py starts the opening mark right after loading this,
    // in the same call, so `holding` only turns true a moment after we exist.
    Component.onCompleted: Qt.callLater(() => { if (!welcome.holding) welcome.enter() })

    ParallelAnimation {
        id: entrance
        NumberAnimation { target: scrim; property: "opacity"; from: 0; to: 1; duration: welcome.stepMs; easing.type: Easing.OutCubic }
        NumberAnimation { target: sheet; property: "opacity"; from: 0; to: 1; duration: welcome.stepMs; easing.type: Easing.OutCubic }
        NumberAnimation { target: rise; property: "y"; to: 0; duration: welcome.reduced ? 0 : theme.motionPage + 60; easing.type: Easing.OutCubic }
        onFinished: if (welcome.step === 0) keysPress.start()
    }
    SequentialAnimation {
        id: exitAnim
        property bool skipped: false
        property bool byKeyboard: false
        ParallelAnimation {
            NumberAnimation { target: welcome; property: "opacity"; to: 0; duration: welcome.reduced ? theme.motionFast : theme.motionBase; easing.type: Easing.InCubic }
        }
        ScriptAction { script: { welcome.finishing(exitAnim.byKeyboard); backend.finishWelcome(exitAnim.skipped, welcome.step) } }
    }

    Keys.onEscapePressed: leave(true, true)

    // ------------------------------------------------------------------ the keyboard stays in the sheet
    // Tab cycles Skip → the step → Back → Continue → Skip (KeyNavigation on Skip and Continue),
    // and if anything else still takes the focus while the sheet is up (a control under the
    // scrim), it comes straight back to the step. Its own pop-up menus (in the overlay) are fine.
    function holds(item) {
        for (let p = item; p; p = p.parent)
            if (p === welcome || p === T.Overlay.overlay) return true
        return false
    }
    function reclaim() {  // later, once the focus has settled (it passes through the scopes on its way)
        const f = welcome.Window.activeFocusItem
        if (f && !welcome.holds(f) && welcome.entered && !welcome.holding && !welcome.leaving) welcome.focusStep()
    }
    Connections {
        target: welcome.Window.window
        enabled: welcome.entered && !welcome.holding && !welcome.leaving
        function onActiveFocusItemChanged() { Qt.callLater(welcome.reclaim) }
    }

    // ------------------------------------------------------------------ the scrim and the sheet
    Rectangle {
        id: scrim
        anchors.fill: parent
        opacity: 0
        color: theme.mode === "dark" ? Qt.rgba(0, 0, 0, 0.72) : Qt.rgba(0, 0, 0, 0.22)
        MouseArea {  // the app underneath waits: clicks and scrolling stop here
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            hoverEnabled: true
            onWheel: (wheel) => wheel.accepted = true
        }
    }

    Item {
        id: sheet
        objectName: "welcomeSheet"
        // 600 × 500 at 100 % text; it grows with Windows' Text size to fit the tallest step (so
        // nothing is clipped), up to the window less 24 px a side. Past that a step scrolls.
        width: Math.min(Math.round(600 * Math.min(1.25, theme.textScale)), welcome.width - 48)
        height: Math.min(welcome.height - 48, Math.max(500, Math.ceil(stage.need) + stage.anchors.topMargin + stage.anchors.bottomMargin))
        anchors.centerIn: parent
        opacity: 0
        transform: Translate { id: rise }
        Accessible.role: Accessible.Dialog
        Accessible.name: "Welcome to Vocet"

        C.Surface { anchors.fill: parent; level: 2; radius: theme.radiusDialog }
        MouseArea { anchors.fill: parent }  // clicks on the sheet's empty parts don't reach the scrim

        C.Button {  // always there
            id: skipButton
            objectName: "welcomeSkip"
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: theme.space5
            anchors.rightMargin: theme.space5
            text: "Skip"
            kind: "plain"
            small: true
            accessibleName: "Skip the welcome"
            KeyNavigation.backtab: primary        // Shift+Tab from the first control wraps to the last
            onClicked: welcome.leave(true)
        }

        Item {
            id: stage
            anchors.fill: parent
            anchors.topMargin: 56
            anchors.bottomMargin: 88
            anchors.leftMargin: theme.space9 - bleed
            anchors.rightMargin: theme.space9 - bleed
            clip: true
            // the stage clips (the steps slide), so a focus ring (4 px outside its field, 2 px wide)
            // needs this much room on each side, or its left and right edges are cut off
            readonly property int bleed: 6
            // the tallest step's content, so the sheet keeps one size as you go through them
            readonly property real need: Math.max(s0.need, s1.need, s2.need, s3.need)
            StepPage { id: s0; index: 0; content: hello }
            StepPage { id: s1; index: 1; content: voice }
            StepPage { id: s2; index: 2; content: tryIt }
            StepPage { id: s3; index: 3; content: extras }
        }

        // the footer: page dots, Back, Continue
        RowLayout {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: theme.space9
            anchors.rightMargin: theme.space7
            anchors.bottomMargin: theme.space7
            spacing: theme.space3

            Row {
                id: dots
                spacing: 6
                Layout.alignment: Qt.AlignVCenter
                Accessible.role: Accessible.StaticText
                Accessible.name: "Step " + (welcome.step + 1) + " of " + welcome.count
                Repeater {
                    model: welcome.count
                    Rectangle {
                        required property int index
                        readonly property bool on: index === welcome.step
                        width: on ? 18 : 6
                        height: 6
                        radius: 3
                        color: on ? theme.textPrimary : theme.textTertiary
                        Behavior on width { enabled: !welcome.reduced; NumberAnimation { duration: welcome.stepMs; easing.type: Easing.OutCubic } }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            C.Button {
                objectName: "welcomeBack"
                text: "Back"
                visible: welcome.step > 0
                onClicked: welcome.back()
            }
            C.Button {
                id: primary
                objectName: "welcomeContinue"
                kind: "primary"
                text: welcome.step === welcome.count - 1 ? "Start using Vocet" : "Continue"
                KeyNavigation.tab: skipButton         // …and Tab from the last back to the first
                onClicked: welcome.next()
            }
        }
    }

    // ------------------------------------------------------------------ one step's page
    component StepPage: Item {
        id: pg
        required property int index
        property Component content
        readonly property bool current: welcome.step === index
        width: stage.width
        height: stage.height
        visible: opacity > 0.001
        opacity: current ? 1 : 0
        enabled: current
        Behavior on opacity { NumberAnimation { duration: welcome.stepMs; easing.type: Easing.OutCubic } }
        transform: Translate {
            x: pg.current || welcome.reduced ? 0 : (pg.index < welcome.step ? -8 : 8)
            Behavior on x { enabled: !welcome.reduced; NumberAnimation { duration: welcome.stepMs; easing.type: Easing.OutCubic } }
        }
        readonly property real need: loader.item ? loader.item.implicitHeight : 0
        Flickable {  // only scrolls when the window is too short for the step
            id: stepFlick
            anchors.fill: parent
            contentWidth: width
            contentHeight: Math.max(height, pg.need)
            interactive: pg.need > height + 0.5
            boundsBehavior: Flickable.StopAtBounds
            clip: interactive
            T.ScrollBar.vertical: C.ScrollBar { visible: stepFlick.interactive }
            Loader {
                id: loader
                x: stage.bleed
                width: stepFlick.width - 2 * stage.bleed
                height: stepFlick.contentHeight
                sourceComponent: pg.content
            }
        }
    }

    // Text column shared by the steps: a title and one or two sentences.
    component Heading: ColumnLayout {
        id: hd
        property string title: ""
        property string text: ""
        spacing: theme.space3
        Layout.fillWidth: true
        C.Txt { text: hd.title; textStyle: "largeTitle"; heading: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
        C.Txt {
            visible: hd.text !== ""
            text: hd.text
            textStyle: "body"
            tone: "secondary"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }

    // ------------------------------------------------------------------ 1 Hello
    // The keycaps press once, after the sheet has arrived (not looping).
    property bool keysDown: false
    SequentialAnimation {
        id: keysPress
        PauseAnimation { duration: 420 }
        ScriptAction { script: if (!welcome.reduced) welcome.keysDown = true }
        PauseAnimation { duration: 520 }
        ScriptAction { script: welcome.keysDown = false }
    }

    Component {
        id: hello
        Item {
            implicitHeight: helloColumn.implicitHeight + 2 * theme.space4
            ColumnLayout {
                id: helloColumn
                width: parent.width
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -theme.space4
                spacing: 0
                C.Logo { Layout.preferredWidth: 56; Layout.preferredHeight: 46; Layout.alignment: Qt.AlignHCenter }
                C.Txt {
                    Layout.topMargin: theme.space7
                    Layout.fillWidth: true
                    text: "Welcome to Vocet"
                    textStyle: "largeTitle"
                    heading: true
                    horizontalAlignment: Text.AlignHCenter
                }
                C.Txt {
                    Layout.topMargin: theme.space3
                    Layout.fillWidth: true
                    Layout.maximumWidth: 400
                    Layout.alignment: Qt.AlignHCenter
                    text: "Click where you want to type, hold " + welcome.keysName + ", speak, and let go. Your words appear there."
                    textStyle: "body"
                    tone: "secondary"
                    wrapMode: Text.Wrap
                    horizontalAlignment: Text.AlignHCenter
                }
                Row {
                    Layout.topMargin: theme.space7
                    Layout.alignment: Qt.AlignHCenter
                    spacing: theme.space3
                    Accessible.role: Accessible.StaticText
                    Accessible.name: welcome.keysName.replace("Win", "Windows key").replace(" + ", " plus ")
                    Repeater {
                        model: backend.hotkeyKeys
                        Row {
                            required property var modelData
                            required property int index
                            spacing: theme.space3
                            C.Txt {
                                visible: index > 0
                                text: "+"
                                textStyle: "title2"
                                tone: "tertiary"
                                anchors.verticalCenter: parent.verticalCenter
                                Accessible.ignored: true
                            }
                            C.Keycap { large: true; label: modelData; pressed: welcome.keysDown; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
                ColumnLayout {  // two promises, both true of the code
                    Layout.topMargin: theme.space9
                    Layout.alignment: Qt.AlignHCenter
                    spacing: theme.space3
                    Promise { icon: "microphone"; text: "The microphone is only on while you dictate." }
                    Promise { icon: "checkmark"; text: "Free, with no account." }
                }
            }
        }
    }
    component Promise: RowLayout {
        id: pr
        property string icon: ""
        property string text: ""
        spacing: theme.space3
        C.Icon { name: pr.icon; size: 16; color: theme.textSecondary; Layout.alignment: Qt.AlignVCenter }
        C.Txt { text: pr.text; textStyle: "callout"; tone: "secondary" }
    }

    // ------------------------------------------------------------------ 2 Your voice
    readonly property var languageNames: ({ "en": "English", "de": "German", "fr": "French", "es": "Spanish",
                                            "zh": "Chinese", "hi": "Hindi" })
    readonly property var chosenLanguages: backend.settings.languages || ["en"]

    Component {
        id: voice
        ColumnLayout {
            spacing: 0
            Heading { title: "Your voice"; text: "Choose your microphone and the languages you speak." }

            VoiceRow {
                Layout.topMargin: theme.space7
                title: "Microphone"
                description: backend.micTesting ? "Say something. The test stops after 5 seconds."
                                                : "Test it to check that Vocet hears you."
                C.PopUpButton {
                    objectName: "welcomeMic"
                    label: "Microphone"
                    Layout.preferredWidth: 220
                    model: backend.mics
                    textRole: "label"
                    valueRole: "name"
                    value: backend.settings.mic || ""
                    onPicked: (v) => { backend.stopMicTest(); backend.setSetting("mic", v) }
                }
            }
            RowLayout {  // Test microphone, and its meter only while testing
                Layout.topMargin: theme.space3
                spacing: theme.space4
                C.Button {
                    objectName: "welcomeMicTest"
                    text: backend.micTesting ? "Stop test" : "Test microphone"
                    iconName: "microphone"
                    onClicked: backend.toggleMicTest()
                }
                Item {
                    id: meter
                    visible: backend.micTesting
                    Layout.fillWidth: true
                    Layout.preferredHeight: 6
                    Layout.alignment: Qt.AlignVCenter
                    Accessible.role: Accessible.ProgressBar
                    Accessible.name: "Microphone level"
                    Rectangle { anchors.fill: parent; radius: 3; color: theme.fillControl }
                    Rectangle {
                        height: parent.height
                        radius: 3
                        width: Math.max(6, parent.width * backend.micTestLevel)
                        color: theme.accent
                        Behavior on width { enabled: !welcome.reduced; NumberAnimation { duration: 60; easing.type: Easing.OutCubic } }
                    }
                }
                C.Txt {
                    id: micError
                    visible: text !== "" && !backend.micTesting
                    textStyle: "callout"
                    tone: "danger"
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                    Connections { target: backend; function onMicTestFailed(message) { micError.text = message } }
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.topMargin: theme.space6; Layout.bottomMargin: theme.space5; height: 1 / Screen.devicePixelRatio; color: theme.separator }
            VoiceRow {
                title: "Languages you speak"
                description: welcome.chosenLanguages.length === 1
                    ? "Vocet always writes " + welcome.languageNames[welcome.chosenLanguages[0]] + "."
                    : "Vocet picks the language you’re speaking."
                C.MultiPopUpButton {
                    objectName: "welcomeLanguages"
                    label: "Languages you speak"
                    Layout.preferredWidth: 220
                    model: backend.spokenLanguages
                    values: welcome.chosenLanguages
                    onPicked: (values) => backend.setSetting("languages", values)
                }
            }
            Item { Layout.fillHeight: true; Layout.minimumHeight: theme.space5 }
            ModelDownload { Layout.fillWidth: true; showReady: true }
        }
    }
    component VoiceRow: RowLayout {
        id: vr
        property string title: ""
        property string description: ""
        default property alias control: slot.data
        spacing: theme.space6
        Layout.fillWidth: true
        ColumnLayout {
            spacing: theme.space1
            Layout.fillWidth: true
            C.Txt { text: vr.title; textStyle: "body"; semibold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
            C.Txt { text: vr.description; textStyle: "callout"; tone: "secondary"; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
        RowLayout { id: slot; Layout.alignment: Qt.AlignVCenter }
    }

    // ------------------------------------------------------------------ 3 Try it
    property Item practice: null
    Connections {
        target: backend
        // app.py: a dictation was pasted, and whether it went into Vocet's own window. The text is
        // already in the field by then (the paste waits until the field has read it).
        function onDictated(intoVocet) {
            if (intoVocet && welcome.step === 2 && welcome.practice && welcome.practice.text.trim() !== "")
                welcome.tried = true
        }
    }

    Component {
        id: tryIt
        ColumnLayout {
            spacing: 0
            Heading {
                title: "Try it"
                text: welcome.modelReady ? "Your words appear where the cursor is: here, or in the app you’re typing in."
                                         : "You can try it as soon as the speech model is ready."
            }
            C.TextArea {
                id: field
                objectName: "welcomePractice"
                Layout.fillWidth: true
                Layout.topMargin: theme.space7
                minHeight: 112
                maxHeight: 150
                placeholderText: "Click here, hold " + welcome.keysName + " and say something."
                accessibleName: "Practice dictation"
                Component.onCompleted: welcome.practice = field
            }
            RowLayout {
                id: done
                Layout.topMargin: theme.space4
                spacing: theme.space3
                opacity: welcome.tried ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: welcome.stepMs; easing.type: Easing.OutCubic } }
                Accessible.role: Accessible.StaticText
                Accessible.name: welcome.tried ? "That’s it." : ""
                onOpacityChanged: if (opacity === 1) Accessible.announce("That’s it.")
                Rectangle {
                    implicitWidth: 22
                    implicitHeight: 22
                    radius: 11
                    color: theme.accent
                    scale: welcome.tried || welcome.reduced ? 1 : 0.6
                    Behavior on scale { NumberAnimation { duration: theme.motionReveal; easing.type: Easing.OutBack } }
                    C.Icon { anchors.centerIn: parent; name: "checkmark"; size: 12; color: theme.onAccent }
                }
                C.Txt { text: "That’s it."; textStyle: "headline" }
            }
            Item { Layout.fillHeight: true }
            C.Txt {
                text: backend.hotkeyIsCombo
                    ? "For longer thoughts, press Space while you hold " + welcome.keysName + ", then let go and keep talking. Press " + welcome.keysName + " again to finish."
                    : "For longer thoughts, double-tap " + welcome.keysName + " and keep talking. Tap it again to finish."
                textStyle: "callout"
                tone: "secondary"
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }
    }

    // ------------------------------------------------------------------ 4 Extras
    readonly property string aiFormattingText:   // as in Settings
        "Tries to fix spelling, lists and self-corrections, on your PC. If you keep history, your original words stay on Home."
    Component {
        id: extras
        ColumnLayout {
            spacing: 0
            Heading { title: "Two extras"; text: "Both are optional. You can change them any time in Settings." }
            VoiceRow {
                Layout.topMargin: theme.space7
                title: "AI formatting"
                description: (backend.aiFormattingStatus === "On" ? "On. " + welcome.aiFormattingText
                             : backend.aiFormattingStatus !== "" ? backend.aiFormattingStatus
                             : welcome.aiFormattingText)
                             + (backend.aiFormattingLanguageNote !== "" ? " " + backend.aiFormattingLanguageNote : "")
                C.Switch {
                    objectName: "welcomeAi"
                    label: "AI formatting"
                    checked: backend.settings.ai_formatting === true
                    enabled: checked || backend.aiFormattingAvailable
                    onToggled: backend.setSetting("ai_formatting", checked)
                }
            }
            Rectangle { Layout.fillWidth: true; Layout.topMargin: theme.space5; Layout.bottomMargin: theme.space5; height: 1 / Screen.devicePixelRatio; color: theme.separator }
            VoiceRow {
                title: "Start Vocet with Windows"
                description: "Vocet waits in the tray, ready for your shortcut."
                C.Switch {
                    objectName: "welcomeStartup"
                    label: "Start Vocet with Windows"
                    checked: backend.settings.start_with_windows === true
                    onToggled: backend.setSetting("start_with_windows", checked)
                }
            }
            Item { Layout.fillHeight: true }
        }
    }
}
