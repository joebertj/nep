import AppKit
import Foundation

let args = CommandLine.arguments
if args.count != 3 { fatalError("Usage: build_dpwh_office_change_share_cards.swift <payload.json> <output-directory>") }
let payload = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[1]))) as! [String: Any]
let output = URL(fileURLWithPath: args[2])
let projects = payload["projects"] as? [[String: Any]] ?? []
let offices = payload["offices"] as? [String: [String: Any]] ?? [:]
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let width: CGFloat = 1200, height: CGFloat = 630
func color(_ hex: UInt32) -> NSColor { NSColor(calibratedRed: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255, blue: CGFloat(hex & 255)/255, alpha: 1) }
func drawText(_ value: String, x: CGFloat, y: CGFloat, size: CGFloat, weight: NSFont.Weight = .regular, ink: NSColor = color(0x212121), maxWidth: CGFloat? = nil) {
    let font = NSFont.systemFont(ofSize: size, weight: weight)
    let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: ink]
    let text = value as NSString
    if let maxWidth {
        let rect = NSRect(x: x, y: y, width: maxWidth, height: 58)
        text.draw(with: rect, options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine], attributes: attrs)
    } else { text.draw(at: NSPoint(x: x, y: y), withAttributes: attrs) }
}
func drawOffice(_ office: [String: Any]?, rect: NSRect, side: Int) {
    color(0xFAFAFA).setFill(); NSBezierPath(roundedRect: rect, xRadius: 12, yRadius: 12).fill()
    color(0xE0E0E0).setStroke(); NSBezierPath(roundedRect: rect, xRadius: 12, yRadius: 12).stroke()
    guard let office, let rings = office["rings"] as? [[[Double]]], !rings.isEmpty else { return }
    let points = rings.flatMap { $0 }.filter { $0.count >= 2 }
    guard let minX = points.map({$0[0]}).min(), let maxX = points.map({$0[0]}).max(), let minY = points.map({$0[1]}).min(), let maxY = points.map({$0[1]}).max() else { return }
    let pad: CGFloat = 24, sx = (rect.width-pad*2)/max(CGFloat(maxX-minX), 0.00001), sy = (rect.height-pad*2)/max(CGFloat(maxY-minY), 0.00001), scale = min(sx,sy)
    let fill = side == 0 ? color(0xDBEAFE) : color(0xFDE68A), stroke = side == 0 ? color(0x0038A8) : color(0xCE1126)
    fill.setFill(); stroke.setStroke()
    for ring in rings {
        let path = NSBezierPath(); path.lineWidth = 2
        for (i,p) in ring.enumerated() where p.count >= 2 {
            let q = NSPoint(x: rect.minX+pad+(CGFloat(p[0])-CGFloat(minX))*scale, y: rect.minY+pad+(CGFloat(p[1])-CGFloat(minY))*scale)
            if i == 0 { path.move(to:q) } else { path.line(to:q) }
        }
        path.close(); path.fill(); path.stroke()
    }
}
func drawRepresentative(_ cards: [[String: Any]], rect: NSRect, label: String) {
    drawText(label, x: rect.minX, y: rect.maxY-22, size: 15, weight: .bold, ink: color(0x0038A8))
    if cards.isEmpty { drawText("No single seat resolved from the boundary", x: rect.minX, y: rect.minY+20, size: 13, ink: color(0x616161), maxWidth: rect.width); return }
    var y = rect.maxY - 112
    for rep in cards.prefix(2) {
        let photoPath = (rep["cachedPhotoUrl"] as? String).map { URL(fileURLWithPath: args[2]).appendingPathComponent(($0 as NSString).lastPathComponent).path }
        if let photoPath, let image = NSImage(contentsOfFile: photoPath) { image.draw(in: NSRect(x: rect.minX, y: y-5, width: 54, height: 64), from: .zero, operation: .sourceOver, fraction: 1) }
        let name = rep["name"] as? String ?? "Representative"
        drawText(name, x: rect.minX+66, y: y+31, size: 14, weight: .bold, maxWidth: rect.width-68)
        drawText(rep["district"] as? String ?? "District", x: rect.minX+66, y: y+12, size: 11, ink: color(0x616161), maxWidth: rect.width-68)
        y -= 72
    }
}
for project in projects {
    let slug = project["shareSlug"] as? String ?? "office-change"
    let title = project["title"] as? String ?? "DPWH office assignment change"
    let nep = project["nepOffice"] as? String ?? "NEP office"
    let hgab = project["hgabOffice"] as? String ?? "HGAB 3rd office"
    let nepAmount = project["nepAmountPesos"] as? Double ?? Double((project["nepAmountPesos"] as? Int) ?? 0)
    let hgabAmount = project["hgabAmountPesos"] as? Double ?? Double((project["hgabAmountPesos"] as? Int) ?? 0)
    let delta = hgabAmount-nepAmount
    let image = NSImage(size: NSSize(width:width,height:height)); image.lockFocus()
    color(0xFAFAFA).setFill(); NSBezierPath(rect:NSRect(x:0,y:0,width:width,height:height)).fill()
    color(0x00246A).setFill(); NSBezierPath(rect:NSRect(x:0,y:488,width:width,height:142)).fill()
    drawText("DPWH OFFICE CHANGES · NEP → HGAB 3RD", x:42, y:594, size:15, weight:.bold, ink:color(0xFCD116))
    drawText(title, x:42, y:526, size:25, weight:.bold, ink:.white, maxWidth:1110)
    let left = NSRect(x:42,y:220,width:522,height:245), right = NSRect(x:636,y:220,width:522,height:245)
    drawOffice(offices[nep],rect:left,side:0); drawOffice(offices[hgab],rect:right,side:1)
    drawText("NEP · \(nep)",x:54,y:438,size:14,weight:.bold,ink:color(0x0038A8),maxWidth:495)
    drawText("HGAB 3RD · \(hgab)",x:648,y:438,size:14,weight:.bold,ink:color(0xCE1126),maxWidth:495)
    drawText("→",x:576,y:310,size:36,weight:.bold,ink:color(0x0038A8))
    let nreps = project["nepRepresentatives"] as? [[String:Any]] ?? [], hreps = project["hgabRepresentatives"] as? [[String:Any]] ?? []
    drawRepresentative(nreps,rect:NSRect(x:42,y:65,width:522,height:130),label:"From · NEP office geography")
    drawRepresentative(hreps,rect:NSRect(x:636,y:65,width:522,height:130),label:"To · HGAB 3rd office geography")
    color(0xE0E0E0).setFill(); NSBezierPath(rect:NSRect(x:42,y:49,width:1116,height:1)).fill()
    drawText("Allocation change",x:42,y:24,size:12,weight:.bold,ink:color(0x616161))
    drawText(String(format:"%@₱%.0f", delta < 0 ? "−" : "+", abs(delta)),x:165,y:18,size:21,weight:.bold,ink:color(0x0038A8))
    drawText("Geographic boundary association · not project sponsorship",x:660,y:24,size:12,ink:color(0x616161))
    image.unlockFocus()
    guard let tiff=image.tiffRepresentation, let bitmap=NSBitmapImageRep(data:tiff), let png=bitmap.representation(using:.png,properties:[:]) else { fatalError("Could not render \(slug)") }
    try png.write(to:output.appendingPathComponent("\(slug).png"))
}
