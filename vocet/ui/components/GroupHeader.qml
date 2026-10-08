// A group header on its own, for ListView sections (history: one box per day), where the
// rows paint the box (C.Row { boxed: true }). Opaque bgWindow, so it can stick while its day
// scrolls (section.labelPositioning: ViewSection.InlineLabels | ViewSection.CurrentLabelAtStart);
// while `stuck`, a 12 px fade below it lets the rows go under softly instead of being cut.
//   section.property: "day"
//   section.delegate: C.GroupHeader {
//       required property string section
//       title: section
//       width: ListView.view.width
//       columnX: page.columnX; columnWidth: page.columnWidth
//   }
import QtQuick
import QtQuick.Layouts
import "." as C

Item {
    id: header
    property string title: ""
    property string count: ""
    property real columnX: 0
    property real columnWidth: width
    property real topSpacing: theme.space7      // 24 px from the previous box
    property bool stuck: false                  // held at the top while its day scrolls under it
    implicitWidth: columnWidth
    implicitHeight: topSpacing + label.implicitHeight + theme.space3
    Accessible.role: Accessible.Heading
    Accessible.name: title

    Rectangle { anchors.fill: parent; color: theme.bgWindow }
    Rectangle {  // while stuck, rows fade out under the header instead of being cut at a hard edge
        visible: header.stuck
        y: parent.height
        width: parent.width
        height: theme.space4
        gradient: Gradient {
            GradientStop { position: 0; color: theme.bgWindow }
            GradientStop { position: 1; color: Qt.alpha(theme.bgWindow, 0) }
        }
    }
    RowLayout {
        x: header.columnX + theme.space5
        width: header.columnWidth - 2 * theme.space5
        y: header.topSpacing
        spacing: theme.space4
        C.Txt {
            id: label
            text: header.title
            textStyle: "headline"
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignBaseline
            Accessible.ignored: true
        }
        C.Txt {
            visible: header.count !== ""
            text: header.count
            textStyle: "caption1"
            tone: "secondary"
            tabular: true
            Layout.alignment: Qt.AlignBaseline
        }
    }
}
