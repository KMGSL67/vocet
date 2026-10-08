// A tooltip: level 1, radius 6, 6 × 8 padding, footnote textPrimary, max width 280.
// 500 ms delay, 100 ms fade. Give every icon-only control one, and truncated text too:
//   C.Tooltip { text: "Copy"; visible: control.hovered || control.visualFocus }
// It parents itself to the item it's declared in and appears above it, kept inside the window.
import QtQuick
import QtQuick.Templates as T
import "." as C

T.ToolTip {
    id: tip
    readonly property real maxTextWidth: 280 - leftPadding - rightPadding
    delay: 500
    // Templates give popups no implicit size: take it from the content, as the Qt styles do.
    implicitWidth: Math.max(implicitBackgroundWidth + leftInset + rightInset, contentWidth + leftPadding + rightPadding)
    implicitHeight: Math.max(implicitBackgroundHeight + topInset + bottomInset, contentHeight + topPadding + bottomPadding)
    timeout: -1
    topPadding: 6
    bottomPadding: 6
    leftPadding: 8
    rightPadding: 8
    margins: 6
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent ? -height - 6 : 0
    contentWidth: Math.min(maxTextWidth, Math.ceil(metrics.advanceWidth) + 1)
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutsideParent | T.Popup.CloseOnReleaseOutsideParent

    TextMetrics {
        id: metrics
        text: tip.text
        font.family: theme.footnoteFamily
        font.pixelSize: theme.footnoteSize
        font.weight: theme.footnoteWeight
    }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: theme.motionFast; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: theme.motionFast; easing.type: Easing.InCubic }
    }
    contentItem: C.Txt {
        text: tip.text
        textStyle: "footnote"
        wrapMode: Text.Wrap
    }
    background: C.Surface { level: 1; radius: theme.radiusTooltip }
}
