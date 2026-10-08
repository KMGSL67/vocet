// The text caret for fields: 2 px, textPrimary, the brand's caret. Blinks at the
// system rate and, like Windows' own caret, holds still 5 s after the last keystroke, so a
// focused field left alone costs nothing. Used as cursorDelegate: C.Caret {}
import QtQuick

Rectangle {
    id: caret
    readonly property Item input: parent
    readonly property int halfPeriod: Qt.styleHints.cursorFlashTime / 2
    readonly property bool live: input !== null && input.activeFocus && !input.readOnly
                                 && input.selectionStart === input.selectionEnd && Window.active
    property int elapsed: 0
    width: 2
    color: theme.textPrimary
    visible: live

    function wake() {
        opacity = 1
        elapsed = 0
        if (live && halfPeriod > 0) blink.restart()
        else blink.stop()
    }
    onLiveChanged: wake()
    Connections {
        target: caret.input
        function onCursorPositionChanged() { caret.wake() }
        function onTextChanged() { caret.wake() }
    }
    Timer {
        id: blink
        interval: Math.max(100, caret.halfPeriod)
        repeat: true
        onTriggered: {
            caret.elapsed += interval
            if (caret.elapsed >= 5000 && caret.opacity === 1) { stop(); return }  // SPI_GETCARETTIMEOUT's 5 s
            caret.opacity = caret.opacity === 1 ? 0 : 1
        }
    }
}
