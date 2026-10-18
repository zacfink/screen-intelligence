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

/// A thin line straight across the top of every screen, just under the menu bar, filling left to right as steps
/// finish. It sizes itself to each display, ignores the mouse, and only shows while a task runs (accent colour;
/// green when done, red when stopped, then it fades).
final class ProgressLine {
    var windows: [NSWindow] = []
    var fills: [NSView] = []
    let height: CGFloat = 3

    func layout() {  // one window per screen, rebuilt when screens change
        windows.forEach { $0.orderOut(nil) }
        windows = []; fills = []
        for screen in NSScreen.screens {
            let barHeight = screen.frame.maxY - screen.visibleFrame.maxY  // the menu bar on this display
            let frame = NSRect(x: screen.frame.minX, y: screen.frame.maxY - barHeight - height,
                               width: screen.frame.width, height: height)
            let w = NSWindow(contentRect: frame, styleMask: .borderless, backing: .buffered, defer: false)
            w.isOpaque = false; w.backgroundColor = .clear; w.hasShadow = false
            w.ignoresMouseEvents = true
            w.level = .statusBar
            w.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle, .fullScreenAuxiliary]
            let track = NSView(frame: NSRect(origin: .zero, size: frame.size))
            track.wantsLayer = true
            track.layer?.backgroundColor = NSColor.labelColor.withAlphaComponent(0.08).cgColor
            let fill = NSView(frame: NSRect(x: 0, y: 0, width: 0, height: height))
            fill.wantsLayer = true
            fill.layer?.cornerRadius = height / 2
            track.addSubview(fill)
            w.contentView = track
            windows.append(w); fills.append(fill)
        }
    }

    func show(state: String, fraction: Double) {
        if windows.count != NSScreen.screens.count { layout() }
        let color: NSColor = state == "done" ? .systemGreen : state == "stopped" ? .systemRed : .controlAccentColor
        let visible = state == "running" || state == "done" || state == "stopped"
        for (w, fill) in zip(windows, fills) {
            fill.layer?.backgroundColor = color.cgColor
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.35
                fill.animator().frame.size.width = w.frame.width * CGFloat(max(0, min(1, fraction)))
                w.animator().alphaValue = visible ? 1 : 0
            }
            if visible { w.orderFrontRegardless() }
        }
    }
}

final class App: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let line = ProgressLine()
    var last: Double = 0

    func applicationDidFinishLaunching(_ note: Notification) {
        line.layout()
        NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification,
                                               object: nil, queue: .main) { _ in self.line.layout() }
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
        // done/stopped show for 10 s across the top, then the line fades; the menu bar item keeps it for a minute
        let recent = Date().timeIntervalSince1970 - (s?.updated ?? 0) < 10
        let fraction = state == "running" ? Double(max(0, (s?.n ?? 1) - 1)) / Double(max(1, s?.of ?? 1)) : 1
        line.show(state: state == "running" || recent ? state : "idle", fraction: fraction)
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
