// Text in one of the named styles of the type ramp: family, size, weight and
// line height come from theme, already multiplied by Windows' Text size.
//   C.Txt { textStyle: "headline"; text: "Dictation" }
//   C.Txt { textStyle: "footnote"; tone: "secondary"; text: "…" }
// tone: primary | secondary | tertiary | disabled | accent | danger | onAccent.
// Tertiary is only for text nobody can hover, press or select (placeholders, the "+"
// between keycaps, the weekly count); anything inside a row, menu or control uses secondary.
// Semibold: don't set font.weight yourself. Qt 6.11 draws "Segoe UI Variable Text" at 600 as
// Bold, so semibold styles use the "… Semibold" family; `semibold: true` does the same for any
// style (a "body strong").
import QtQuick

Text {
    id: txt
    property string textStyle: "body"
    property string tone: "primary"
    property bool heading: false       // announced as a heading by screen readers
    property bool tabular: false       // tabular figures, so times and counts align
    property bool semibold: theme[textStyle + "Weight"] >= 600
    font.family: semibold ? theme[textStyle + "Family"] + " Semibold" : theme[textStyle + "Family"]
    font.pixelSize: theme[textStyle + "Size"]
    font.weight: semibold ? Font.DemiBold : Font.Normal
    font.features: tabular ? { "tnum": 1 } : ({})
    lineHeight: theme[textStyle + "Line"]
    lineHeightMode: Text.FixedHeight
    textFormat: Text.PlainText
    color: tone === "secondary" ? theme.textSecondary
         : tone === "tertiary" ? theme.textTertiary
         : tone === "disabled" ? theme.textDisabled
         : tone === "accent" ? theme.accentText
         : tone === "danger" ? theme.dangerText
         : tone === "onAccent" ? theme.onAccent
         : theme.textPrimary
    Accessible.role: heading ? Accessible.Heading : Accessible.StaticText
    Accessible.name: text
}
