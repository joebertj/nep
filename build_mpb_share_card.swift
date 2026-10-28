import AppKit
import Foundation

let args = CommandLine.arguments
if args.count != 4 {
    fatalError("Usage: build_mpb_share_card.swift <proximity.json> <boundaries.json> <output.png>")
}
let input = URL(fileURLWithPath: args[1])
let boundariesInput = URL(fileURLWithPath: args[2])
let output = URL(fileURLWithPath: args[3])
let payload = try JSONSerialization.jsonObject(with: Data(contentsOf: input)) as! [String: Any]
let projects = payload["projectDetails"] as? [String: [String: Any]] ?? [:]
let points: [(Double, Double)] = projects.values.compactMap { project in
    guard let coordinate = project["coordinate"] as? [String: Any],
          let lat = coordinate["latitude"] as? Double,
          let lon = coordinate["longitude"] as? Double else { return nil }
    return (lon, lat)
}
let boundaryPayload = try JSONSerialization.jsonObject(with: Data(contentsOf: boundariesInput)) as! [String: Any]
let features = boundaryPayload["features"] as? [[String: Any]] ?? []

let width = 1200
let height = 630
let image = NSImage(size: NSSize(width: width, height: height))
image.lockFocus()

func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255) / 255,
            green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: 1)
}
func text(_ value: String, x: CGFloat, y: CGFloat, font: NSFont, foreground: NSColor) {
    (value as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [.font: font, .foregroundColor: foreground])
}

let navy = color(0x00246A)
let panel = color(0x0038A8)
let pale = color(0xEAF0FF)
let muted = color(0xB9C9E8)
let blue = color(0x5B8DE8)
let gold = color(0xFCD116)
NSColor.white.setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()
navy.setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()

// Left panel carries the share message; right panel plots only project coordinates.
text("BETTERGOV.PH  /  FY2027", x: 64, y: 550, font: .boldSystemFont(ofSize: 17), foreground: gold)
text("DPWH multi-purpose", x: 64, y: 475, font: .boldSystemFont(ofSize: 39), foreground: pale)
text("building locations", x: 64, y: 427, font: .boldSystemFont(ofSize: 39), foreground: pale)
text("Where listed project coordinates cluster", x: 66, y: 373, font: .systemFont(ofSize: 19), foreground: muted)
text("\(points.count.formatted()) projects with printed coordinates", x: 66, y: 315, font: .boldSystemFont(ofSize: 17), foreground: gold)
text("Same-site, proximity and boundary review", x: 66, y: 285, font: .systemFont(ofSize: 15), foreground: pale)
text("Proposed allocations · review leads, not findings", x: 66, y: 72, font: .systemFont(ofSize: 14), foreground: muted)

let plot = NSRect(x: 570, y: 35, width: 590, height: 500)
panel.setFill()
NSBezierPath(roundedRect: plot, xRadius: 20, yRadius: 20).fill()
// Grid lines make clear this is a coordinate plot, not a rendered basemap.
let grid = NSBezierPath()
grid.lineWidth = 1
for i in 1...4 {
    let x = plot.minX + plot.width * CGFloat(i) / 5
    let y = plot.minY + plot.height * CGFloat(i) / 5
    grid.move(to: NSPoint(x: x, y: plot.minY + 12)); grid.line(to: NSPoint(x: x, y: plot.maxY - 12))
    grid.move(to: NSPoint(x: plot.minX + 12, y: y)); grid.line(to: NSPoint(x: plot.maxX - 12, y: y))
}
color(0x244782).setStroke(); grid.stroke()
let minLon = 116.0, maxLon = 128.0, minLat = 4.0, maxLat = 22.0
func mapPoint(_ lon: Double, _ lat: Double) -> NSPoint {
    NSPoint(x: plot.minX + 18 + (lon - minLon) / (maxLon - minLon) * (plot.width - 36),
            y: plot.minY + 18 + (lat - minLat) / (maxLat - minLat) * (plot.height - 36))
}
let islands = NSBezierPath()
for feature in features {
    guard let rings = feature["rings"] as? [[[Double]]] else { continue }
    for ring in rings {
        guard let first = ring.first, first.count >= 2,
              first[0] >= minLon - 0.3, first[0] <= maxLon + 0.3,
              first[1] >= minLat - 0.3, first[1] <= maxLat + 0.3 else { continue }
        let start = mapPoint(first[0], first[1])
        islands.move(to: start)
        for pair in ring.dropFirst() where pair.count >= 2 {
            let p = mapPoint(pair[0], pair[1])
            islands.line(to: p)
        }
        islands.close()
    }
}
color(0x4778C7).setFill(); islands.fill()
blue.withAlphaComponent(0.8).setStroke(); islands.lineWidth = 0.65; islands.stroke()
for (lon, lat) in points {
    guard lon >= minLon, lon <= maxLon, lat >= minLat, lat <= maxLat else { continue }
    let p = mapPoint(lon, lat)
    let x = p.x
    let y = p.y
    let dot = NSBezierPath(ovalIn: NSRect(x: x - 2.4, y: y - 2.4, width: 4.8, height: 4.8))
    gold.withAlphaComponent(0.9).setFill(); dot.fill()
}
text("Listed coordinates · Philippines", x: 613, y: 548, font: .boldSystemFont(ofSize: 15), foreground: pale)
text("Municipal boundaries · DPWH GIS", x: 593, y: 15, font: .systemFont(ofSize: 12), foreground: muted)

image.unlockFocus()
let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
let png = rep.representation(using: .png, properties: [:])!
try png.write(to: output, options: .atomic)
