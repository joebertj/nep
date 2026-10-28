import AppKit
import Foundation

let args = CommandLine.arguments
if args.count != 4 {
    fatalError("Usage: build_out_of_place_og_card.swift <projects.json> <boundaries.json> <output.png>")
}
let payload = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[1]))) as! [String: Any]
let boundaryPayload = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[2]))) as! [String: Any]
let projects = payload["projects"] as? [[String: Any]] ?? []
let features = boundaryPayload["national"] as? [[String: Any]] ?? []
let width: CGFloat = 1200, height: CGFloat = 630

func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255) / 255,
            green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: 1)
}
func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ font: NSFont, _ foreground: NSColor) {
    (value as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [.font: font, .foregroundColor: foreground])
}

let navy = color(0x00246A), panel = color(0x0038A8), pale = color(0xEAF0FF)
let muted = color(0xB9C9E8), boundary = color(0x5B8DE8), gold = color(0xFCD116), red = color(0xCE1126)
let image = NSImage(size: NSSize(width: width, height: height))
image.lockFocus()
navy.setFill(); NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()

text("BETTERGOV.PH  /  FY2027 DPWH", 58, 566, .boldSystemFont(ofSize: 16), gold)
text("Out of place?", 58, 492, .boldSystemFont(ofSize: 40), pale)
text("Project coordinates", 60, 438, .boldSystemFont(ofSize: 28), pale)
text("and intended locations", 60, 402, .boldSystemFont(ofSize: 28), pale)
text("\(projects.count.formatted()) coordinate-bearing projects", 60, 335, .boldSystemFont(ofSize: 17), gold)
text("Compare printed coordinates with", 60, 301, .systemFont(ofSize: 16), pale)
text("the project-named locality.", 60, 276, .systemFont(ofSize: 16), pale)
text("HGAB 3rd · location review", 60, 196, .systemFont(ofSize: 14), muted)
text("Review leads, not findings", 60, 72, .systemFont(ofSize: 14), muted)

let plot = NSRect(x: 500, y: 35, width: 660, height: 525)
panel.setFill(); NSBezierPath(roundedRect: plot, xRadius: 18, yRadius: 18).fill()
let minLon = 116.0, maxLon = 128.0, minLat = 4.0, maxLat = 22.0
func mapPoint(_ lon: Double, _ lat: Double) -> NSPoint {
    NSPoint(x: plot.minX + 20 + (lon - minLon) / (maxLon - minLon) * (plot.width - 40),
            y: plot.minY + 20 + (lat - minLat) / (maxLat - minLat) * (plot.height - 40))
}
let islands = NSBezierPath()
for feature in features {
    guard let rings = feature["rings"] as? [[[Double]]] else { continue }
    for ring in rings where ring.count > 2 {
        guard let first = ring.first, first.count >= 2,
              first[0] >= minLon - 0.3, first[0] <= maxLon + 0.3,
              first[1] >= minLat - 0.3, first[1] <= maxLat + 0.3 else { continue }
        islands.move(to: mapPoint(first[0], first[1]))
        for point in ring.dropFirst() where point.count >= 2 { islands.line(to: mapPoint(point[0], point[1])) }
        islands.close()
    }
}
color(0x4778C7).setFill(); islands.fill()
boundary.withAlphaComponent(0.82).setStroke(); islands.lineWidth = 0.55; islands.stroke()

for project in projects {
    guard let lat = project["latitude"] as? Double, let lon = project["longitude"] as? Double,
          lon >= minLon, lon <= maxLon, lat >= minLat, lat <= maxLat else { continue }
    let point = mapPoint(lon, lat)
    let dot = NSBezierPath(ovalIn: NSRect(x: point.x - 3.2, y: point.y - 3.2, width: 6.4, height: 6.4))
    gold.withAlphaComponent(0.95).setFill(); dot.fill()
}
text("HGAB 3rd DPWH · coordinate review", 525, 575, .boldSystemFont(ofSize: 14), pale)
text("Municipal boundaries and listed project points", 525, 15, .systemFont(ofSize: 12), muted)
image.unlockFocus()

let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
let png = bitmap.representation(using: .png, properties: [:])!
try png.write(to: URL(fileURLWithPath: args[3]), options: .atomic)
