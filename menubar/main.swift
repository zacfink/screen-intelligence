// Claude's status in the menu bar: what desk (or any long task) is doing right now, read from
// ~/Projects/screen-intelligence/runtime/status.json. Native look: SF Symbols, system font, template icons.
// Build: menubar/build.sh  ·  Stop in the menu writes runtime/stop, which desk checks before every step.
import AppKit

let runtime = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Projects/screen-intelligence/runtime")
let statusFile = runtime.appendingPathComponent("status.json")
let stopFile = runtime.appendingPathComponent("stop")

struct Status: Decodable {
    var state: String          // running | done | stopped | idle
    var task: String?
    var step: String?
    var n: Int?
    var of: Int?
    var updated: Double
    var log: [String]?
}

final class App: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var last: Double = 0

    func applicationDidFinishLaunching(_ note: Notification) {
        refresh()
        Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { _ in self.refresh() }
    }

    func symbol(_ name: String) -> NSImage? {
        let image = NSImage(systemSymbolName: name, accessibilityDescription: "Claude")
        image?.isTemplate = true
        return image
    }

    func refresh() {
        guard let data = try? Data(contentsOf: statusFile),
              var s = try? JSONDecoder().decode(Status.self, from: data) else { show(nil); return }
        // a finished task fades back to idle after a minute; a run that went quiet for 5 min is shown as stale
        let age = Date().timeIntervalSince1970 - s.updated
        if s.state != "running" && age > 60 { s.state = "idle" }
        if s.state == "running" && age > 300 { s.state = "stopped"; s.step = "No update for 5 min" }
        show(s)
    }

    func show(_ s: Status?) {
        guard let button = item.button else { return }
        let state = s?.state ?? "idle"
        let icon = ["running": "cursorarrow.motionlines", "done": "checkmark.circle",
                    "stopped": "exclamationmark.triangle"][state] ?? "sparkle"
        button.image = symbol(icon)
        button.imagePosition = .imageLeading
        var title = ""
        if state == "running", let n = s?.n, let of = s?.of { title = " \(n)/\(of)" }
        else if state == "done" { title = " Done" }
        else if state == "stopped" { title = " Stopped" }
        button.attributedTitle = NSAttributedString(string: title, attributes: [
            .font: NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)])
        button.contentTintColor = state == "stopped" ? .systemRed : nil
        guard s?.updated != last || item.menu == nil else { return }
        last = s?.updated ?? 0
        item.menu = menu(s, state: state)
    }

    func menu(_ s: Status?, state: String) -> NSMenu {
        let menu = NSMenu()
        let header = NSMenuItem(title: s?.task ?? "Claude is idle", action: nil, keyEquivalent: "")
        header.attributedTitle = NSAttributedString(string: s?.task ?? "Claude is idle",
                                                    attributes: [.font: NSFont.boldSystemFont(ofSize: NSFont.systemFontSize)])
        menu.addItem(header)
        if let step = s?.step { menu.addItem(withTitle: step, action: nil, keyEquivalent: "") }
        if let log = s?.log, !log.isEmpty {
            menu.addItem(.separator())
            for line in log.suffix(10) {
                let row = NSMenuItem(title: line, action: nil, keyEquivalent: "")
                row.attributedTitle = NSAttributedString(string: line, attributes: [
                    .font: NSFont.systemFont(ofSize: NSFont.smallSystemFontSize), .foregroundColor: NSColor.secondaryLabelColor])
                menu.addItem(row)
            }
        }
        menu.addItem(.separator())
        let stop = NSMenuItem(title: "Stop After This Step", action: #selector(stopTask), keyEquivalent: ".")
        stop.target = self
        stop.isEnabled = state == "running"
        menu.addItem(stop)
        let quit = NSMenuItem(title: "Quit Claude Status", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.addItem(quit)
        menu.autoenablesItems = false
        return menu
    }

    @objc func stopTask() { FileManager.default.createFile(atPath: stopFile.path, contents: Data()) }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)  // menu bar only, no Dock icon
app.run()
