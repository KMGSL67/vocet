// An inset grouped section, the workhorse: header, box, footer.
// Header: headline textPrimary, sentence case, inset 16, 8 px above the box, optional trailing
// count (caption1 textSecondary). Box: a glass card (C.Glass kind "card"), radius 18.
// Footer: footnote textSecondary, inset 16, 6 px below the box, max 2 lines; it explains
// consequences, and hosts transient notes (footerIcon: "info"). C.Page puts 24 px between groups.
//   C.Group {
//       title: "Dictation"; footer: "Automatic writes English or German, whichever you speak."
//       C.SettingRow { title: "Hands-free"; C.Switch { … } }
//       C.SettingRow { title: "Language";   C.Segmented { … } }
//   }
// Rows go straight in (C.Row, C.SettingRow, C.ChoiceRow, or a Repeater of them); the group
// marks the first and last visible row, so separators and highlights follow the corners.
import QtQuick
import QtQuick.Layouts
import "." as C

ColumnLayout {
    id: group
    property string title: ""
    property string count: ""          // e.g. "4 words"
    property string footer: ""
    property string footerIcon: ""     // e.g. "info" for a transient note
    property alias box: box
    default property alias rows: rowsColumn.data

    Layout.fillWidth: true
    spacing: 0
    Accessible.role: Accessible.Grouping
    Accessible.name: title

    function relayout() {
        const kids = []
        for (let i = 0; i < rowsColumn.children.length; i++) {
            const k = rowsColumn.children[i]
            if (k.visible && k.first !== undefined && k.last !== undefined)
                kids.push(k)
        }
        for (let j = 0; j < kids.length; j++) {
            kids[j].first = j === 0
            kids[j].last = j === kids.length - 1
        }
    }

    RowLayout {
        visible: group.title !== ""
        Layout.fillWidth: true
        Layout.leftMargin: theme.space5
        Layout.rightMargin: theme.space5
        Layout.bottomMargin: theme.space3
        spacing: theme.space4
        C.Txt {
            text: group.title
            textStyle: "headline"
            heading: true
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignBaseline
        }
        C.Txt {
            visible: group.count !== ""
            text: group.count
            textStyle: "caption1"
            tone: "secondary"
            tabular: true
            Layout.alignment: Qt.AlignBaseline
        }
    }

    Item {
        id: box
        Layout.fillWidth: true
        implicitHeight: rowsColumn.implicitHeight
        C.Glass { anchors.fill: parent; kind: "card"; radius: theme.radiusGroup }
        ColumnLayout {
            id: rowsColumn
            width: parent.width
            spacing: 0
            onVisibleChildrenChanged: group.relayout()
            Component.onCompleted: group.relayout()
        }
    }

    RowLayout {
        visible: group.footer !== ""
        Layout.fillWidth: true
        Layout.topMargin: 6
        Layout.leftMargin: theme.space5
        Layout.rightMargin: theme.space5
        spacing: 6
        C.Icon {
            visible: group.footerIcon !== ""
            name: group.footerIcon
            size: 12
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 2
        }
        C.Txt {
            text: group.footer
            textStyle: "footnote"
            tone: "secondary"
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.maximumWidth: 560
        }
    }
}
