import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "s3pp3ku.omavoid"
    property string mode: "stock"
    property string lastError: ""
    property string iconPalette: "white"
    property string gamePalette: "teal"
    property bool menuOpen: false
    property var pending: []
    readonly property int iconSize: {
        var size = parseInt(root.setting("iconSize", 12), 10)
        return isFinite(size) ? Math.max(8, Math.min(18, size)) : 12
    }
    readonly property color iconInk: iconPalette === "theme" ? Color.accent
        : iconPalette === "teal" ? "#2eff9c" : "#ffffff"
    readonly property string controller: decodeURIComponent(String(Qt.resolvedUrl("scripts/control.py")).replace(/^file:\/\//, ""))
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function close() { root.menuOpen = false }
    function invoke(action, argumentsList) {
        var command = ["/usr/bin/python", "-B", root.controller, action].concat(argumentsList || [])
        if (worker.running) { root.pending = root.pending.concat([command]); return }
        root.lastError = ""
        worker.command = command
        worker.running = true
    }
    function refresh() { root.invoke("status") }

    Process {
        id: worker
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var result = JSON.parse(text)
                    root.mode = result.mode || "stock"
                    root.lastError = result.error || ""
                    root.iconPalette = result.appearance ? result.appearance.icon : "white"
                    root.gamePalette = result.appearance ? result.appearance.game : "teal"
                } catch (error) { root.lastError = "Unable to read Omarchy: Lunatic Fringe status" }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: if (text.trim()) root.lastError = text.trim()
        }
        onExited: Qt.callLater(function() {
            if (!worker.running && root.pending.length) {
                var next = root.pending[0]
                root.pending = root.pending.slice(1)
                worker.command = next
                worker.running = true
            }
        })
    }
    FileView {
        path: Quickshell.env("HOME") + "/.config/omavoid/screensaver.json"
        watchChanges: true
        printErrors: false
        onFileChanged: root.refresh()
    }
    FileView {
        path: Quickshell.env("HOME") + "/.config/omavoid/appearance.json"
        watchChanges: true
        printErrors: false
        onFileChanged: root.refresh()
    }
    Component.onCompleted: root.refresh()

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        slotSize: Style.space(22)
        opticalSize: Style.space(root.iconSize)
        tooltipText: root.lastError ? "Omarchy: Lunatic Fringe: " + root.lastError
            : "Omarchy: Lunatic Fringe · " + (root.mode === "omavoid" ? "Omarchy: Lunatic Fringe screensaver" : "Stock screensaver")
              + "\nClick: settings · Right-click: play · Middle-click: preview"
        iconComponent: Component {
            Canvas {
                width: Style.space(root.iconSize)
                height: width
                anchors.centerIn: parent
                property color ink: root.iconInk
                onInkChanged: requestPaint()
                onWidthChanged: requestPaint()
                Component.onCompleted: requestPaint()
                onPaint: {
                    var c = getContext("2d")
                    c.reset()
                    c.scale(width / 20, height / 20)
                    c.strokeStyle = ink
                    c.lineWidth = 1.5
                    c.lineJoin = "round"
                    c.beginPath()
                    c.moveTo(10, 1); c.lineTo(18, 18); c.lineTo(10, 13)
                    c.lineTo(2, 18); c.closePath(); c.stroke()
                    c.beginPath(); c.moveTo(10, 6); c.lineTo(10, 11); c.stroke()
                }
            }
        }
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.RightButton) { root.close(); root.invoke("play") }
            else if (mouseButton === Qt.MiddleButton) { root.close(); root.invoke("preview") }
            else if (mouseButton === Qt.LeftButton) { root.refresh(); root.menuOpen = !root.menuOpen }
        }
    }

    component ThemeButton: Button {
        foreground: Color.popups.text
        accent: Color.accent
        bordered: false
    }

    PopupCard {
        id: popup
        anchorItem: button
        owner: root
        bar: root.bar
        open: root.menuOpen
        contentWidth: popup.fittedContentWidth(Style.space(420))
        contentHeight: popup.fittedContentHeight(content.implicitHeight)
        Column {
            id: content
            anchors.fill: parent
            spacing: Style.space(10)
            Text {
                text: "OMARCHY: LUNATIC FRINGE"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                font.bold: true
            }
            ThemeButton {
                width: parent.width
                text: (root.mode === "omavoid" ? "Omarchy: Lunatic Fringe" : "Stock Omarchy") + "  ·  Switch"
                onClicked: root.invoke("toggle")
            }
            Row {
                width: parent.width
                spacing: Style.space(8)
                ThemeButton {
                    width: (parent.width - parent.spacing) / 2
                    text: "Play"
                    onClicked: { root.close(); root.invoke("play") }
                }
                ThemeButton {
                    width: (parent.width - parent.spacing) / 2
                    text: "Preview saver"
                    onClicked: { root.close(); root.invoke("preview") }
                }
            }
            Text {
                text: "Icon color"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
            }
            Row {
                id: iconChoices
                width: parent.width
                spacing: Style.space(5)
                Repeater {
                    model: ["white", "teal", "theme"]
                    delegate: ThemeButton {
                        required property string modelData
                        width: (iconChoices.width - 2 * iconChoices.spacing) / 3
                        text: modelData === "theme" ? "Omarchy" : modelData.charAt(0).toUpperCase() + modelData.slice(1)
                        selected: root.iconPalette === modelData
                        onClicked: { root.iconPalette = modelData; root.invoke("appearance", ["icon", modelData]) }
                    }
                }
            }
            Text {
                text: "Game accents"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
            }
            Row {
                id: gameChoices
                width: parent.width
                spacing: Style.space(5)
                Repeater {
                    model: ["white", "teal", "theme"]
                    delegate: ThemeButton {
                        required property string modelData
                        width: (gameChoices.width - 2 * gameChoices.spacing) / 3
                        text: modelData === "theme" ? "Omarchy" : modelData.charAt(0).toUpperCase() + modelData.slice(1)
                        selected: root.gamePalette === modelData
                        onClicked: { root.gamePalette = modelData; root.invoke("appearance", ["game", modelData]) }
                    }
                }
            }
            Text {
                width: parent.width
                text: root.lastError || "Omarchy follows your active theme. Game changes apply live."
                wrapMode: Text.WordWrap
                color: root.lastError ? Color.urgent : Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
            }
        }
    }
}
