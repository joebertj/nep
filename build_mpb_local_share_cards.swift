import AppKit
import Foundation

let args = CommandLine.arguments
if args.count != 3 { fatalError("Usage: build_mpb_local_share_cards.swift <maps.json> <output-directory>") }
let input = URL(fileURLWithPath: args[1]), outputDir = URL(fileURLWithPath: args[2])
try FileManager.default.createDirectory(at: outputDir, withIntermediateDirectories: true)
let maps = try JSONSerialization.jsonObject(with: Data(contentsOf: input)) as! [[String: Any]]
let W = 1200, H = 630
func color(_ hex: UInt32) -> NSColor { NSColor(calibratedRed: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255, blue: CGFloat(hex & 255)/255, alpha: 1) }
func txt(_ value: String, _ x: CGFloat, _ y: CGFloat, _ font: NSFont, _ color: NSColor) { (value as NSString).draw(at: NSPoint(x:x,y:y), withAttributes:[.font:font,.foregroundColor:color]) }
func distText(_ m: Double) -> String { m >= 1000 ? String(format:"%.1f km",m/1000) : String(format:"%.0f m",m) }
let navy=color(0x00246A), panel=color(0x0038A8), pale=color(0xEAF0FF), muted=color(0xB9C9E8), blue=color(0x5B8DE8), gold=color(0xFCD116), inside=color(0x2459A6), outside=color(0xCE1126)
for map in maps {
    guard let slug=map["slug"] as? String, let title=map["title"] as? String,
          let rawPoints=map["points"] as? [[String:Any]], !rawPoints.isEmpty else { continue }
    let points = rawPoints.compactMap { p -> (String,String,Double,Double,Bool)? in
        guard let id=p["id"] as? String, let name=p["name"] as? String,
              let lon=p["lon"] as? Double, let lat=p["lat"] as? Double else { return nil }
        return (id,name,lon,lat,p["inside"] as? Bool ?? false)
    }
    guard !points.isEmpty else { continue }
    let rings = map["rings"] as? [[[Double]]] ?? []
    let pairs = map["pairs"] as? [[String:Any]] ?? []
    let distances = pairs.compactMap{$0["distance"] as? Double}
    let maxDistance = distances.max() ?? 0
    let minDistance = distances.min() ?? 0
    let centerLat = points.map{$0.3}.reduce(0,+)/Double(points.count)
    let centerLon = points.map{$0.2}.reduce(0,+)/Double(points.count)
    let cosLat = cos(centerLat * Double.pi / 180)
    func xy(_ lon: Double,_ lat: Double)->(Double,Double){((lon-centerLon)*111320*cosLat,(lat-centerLat)*111320)}
    var all = points.map{xy($0.2,$0.3)}
    for ring in rings { all += ring.filter{$0.count>=2}.map{xy($0[0],$0[1])} }
    var minX=all.map{$0.0}.min() ?? -1, maxX=all.map{$0.0}.max() ?? 1, minY=all.map{$0.1}.min() ?? -1, maxY=all.map{$0.1}.max() ?? 1
    if maxX-minX < 1 {minX -= 1;maxX += 1}; if maxY-minY < 1 {minY -= 1;maxY += 1}
    let plot=NSRect(x:550,y:35,width:620,height:520)
    let pad:CGFloat=28, scale=min((plot.width-2*pad)/CGFloat(maxX-minX),(plot.height-2*pad)/CGFloat(maxY-minY))
    let usedW=CGFloat(maxX-minX)*scale, usedH=CGFloat(maxY-minY)*scale
    let left=plot.minX+(plot.width-usedW)/2, bottom=plot.minY+(plot.height-usedH)/2
    func pt(_ lon:Double,_ lat:Double)->NSPoint { let (x,y)=xy(lon,lat); return NSPoint(x:left+CGFloat(x-minX)*scale,y:bottom+CGFloat(y-minY)*scale) }
    let image=NSImage(size:NSSize(width:W,height:H)); image.lockFocus()
    navy.setFill(); NSBezierPath(rect:NSRect(x:0,y:0,width:W,height:H)).fill()
    txt("BETTERGOV.PH  /  FY2027",64,550,.boldSystemFont(ofSize:17),gold)
    txt("MPB project locations",64,475,.boldSystemFont(ofSize:34),pale)
    let titleFont=NSFont.boldSystemFont(ofSize:25)
    let titleLine=(title as NSString).length > 36 ? String(title.prefix(36))+"…" : title
    txt(titleLine,66,430,titleFont,gold)
    txt("\(points.count) plotted projects · \(pairs.count) location pairs",66,370,.systemFont(ofSize:17),muted)
    txt("Farthest pair: \(distText(maxDistance))",66,333,.boldSystemFont(ofSize:16),pale)
    txt("Closest pair: \(distText(minDistance))",66,305,.systemFont(ofSize:15),pale)
    txt("Listed coordinates · boundary review",66,72,.systemFont(ofSize:14),muted)
    panel.setFill(); NSBezierPath(roundedRect:plot,xRadius:18,yRadius:18).fill()
    // Draw municipal outline from saved DPWH/NAMRIA-derived boundary rings.
    let boundary=NSBezierPath()
    for ring in rings where ring.count > 2 {
        for (i,coord) in ring.enumerated() where coord.count>=2 {
            let p=pt(coord[0],coord[1]); if i==0 {boundary.move(to:p)} else {boundary.line(to:p)}
        }
        boundary.close()
    }
    pale.setFill(); boundary.windingRule = .evenOdd; boundary.fill()
    blue.setStroke(); boundary.lineWidth=1.25; boundary.stroke()
    let byId=Dictionary(uniqueKeysWithValues:points.map{($0.0,$0)})
    for pair in pairs {
        guard let aId=pair["left"] as? String,let bId=pair["right"] as? String,
              let a=byId[aId],let b=byId[bId] else {continue}
        let d=pair["distance"] as? Double ?? 0
        let line=NSBezierPath(); line.move(to:pt(a.2,a.3));line.line(to:pt(b.2,b.3));line.lineWidth=d<50 ? 3.5 : 2
        (d<50 ? outside : d>=10000 ? gold : d<1000 ? blue : color(0x244782)).withAlphaComponent(0.85).setStroke();line.stroke()
    }
    for (i,p) in points.enumerated() {
        let center=pt(p.2,p.3), dot=NSBezierPath(ovalIn:NSRect(x:center.x-10,y:center.y-10,width:20,height:20))
        (p.4 ? inside : outside).setFill(); dot.fill(); NSColor.white.setStroke();dot.lineWidth=1.5;dot.stroke()
        let label=String(i+1); let attrs:[NSAttributedString.Key:Any]=[.font:NSFont.boldSystemFont(ofSize:9),.foregroundColor:NSColor.white]
        let size=(label as NSString).size(withAttributes:attrs);(label as NSString).draw(at:NSPoint(x:center.x-size.width/2,y:center.y-size.height/2),withAttributes:attrs)
    }
    txt("Municipal boundary · listed coordinates",575,570,.boldSystemFont(ofSize:14),pale)
    txt("Proposed allocations · review leads, not findings",575,12,.systemFont(ofSize:12),muted)
    image.unlockFocus()
    let rep=NSBitmapImageRep(data:image.tiffRepresentation!)!
    try rep.representation(using:.png,properties:[:])!.write(to:outputDir.appendingPathComponent("\(slug).png"),options:.atomic)
}
