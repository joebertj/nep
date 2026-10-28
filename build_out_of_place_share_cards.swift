import AppKit
import Foundation

let args = CommandLine.arguments
if args.count != 4 { fatalError("Usage: build_out_of_place_share_cards.swift <projects.json> <boundaries.json> <output-directory>") }
let payload = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[1]))) as! [String: Any]
let boundaryPayload = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[2]))) as! [String: Any]
let portraitFiles = payload["portraitFiles"] as? [String: String] ?? [:]
let output = URL(fileURLWithPath: args[3])
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let projects = payload["projects"] as? [[String: Any]] ?? []
let provinceFeatures = boundaryPayload["provinceFeatures"] as? [[String: Any]] ?? []
let nationalFeatures = boundaryPayload["national"] as? [[String: Any]] ?? []
let width: CGFloat = 1200, height: CGFloat = 630
func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255) / 255,
            green: CGFloat((hex >> 8) & 255) / 255,
            blue: CGFloat(hex & 255) / 255, alpha: 1)
}
func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ font: NSFont, _ foreground: NSColor) {
    (value as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: [.font: font, .foregroundColor: foreground])
}
func clippedLines(_ value: String, maxChars: Int, maxLines: Int) -> [String] {
    let words = value.split(whereSeparator: \.isWhitespace).map(String.init)
    var lines: [String] = [], current = ""
    for word in words {
        let candidate = current.isEmpty ? word : current + " " + word
        if candidate.count > maxChars && !current.isEmpty { lines.append(current); current = word }
        else { current = candidate }
    }
    if !current.isEmpty { lines.append(current) }
    if lines.count > maxLines {
        lines = Array(lines.prefix(maxLines))
        lines[maxLines - 1] = String(lines[maxLines - 1].prefix(max(0, maxChars - 1))) + "…"
    }
    return lines
}
func drawPortrait(_ image: NSImage, in rect: NSRect) {
    guard image.size.width > 0, image.size.height > 0 else { return }
    let targetRatio = rect.width / rect.height
    let imageRatio = image.size.width / image.size.height
    var source = NSRect(origin: .zero, size: image.size)
    if imageRatio > targetRatio {
        source.size.width = image.size.height * targetRatio
        source.origin.x = (image.size.width - source.size.width) / 2
    } else {
        source.size.height = image.size.width / targetRatio
        source.origin.y = (image.size.height - source.size.height) / 2
    }
    NSGraphicsContext.saveGraphicsState()
    let clip = NSBezierPath(roundedRect: rect, xRadius: 8, yRadius: 8)
    clip.addClip()
    image.draw(in: rect, from: source, operation: .sourceOver, fraction: 1)
    NSGraphicsContext.restoreGraphicsState()
    NSColor(calibratedWhite: 1, alpha: 0.8).setStroke()
    clip.lineWidth = 1.5
    clip.stroke()
}
func norm(_ value: String) -> String {
    let folded = value.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
    return folded.lowercased().replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
}
func featurePlace(_ feature: [String: Any]) -> String? {
    (feature["city"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? (feature["municipality"] as? String)
}
func isNamedIntended(_ project: [String: Any], _ feature: [String: Any]) -> Bool {
    guard let rawPlace = featurePlace(feature) else { return false }
    let base = norm(rawPlace.replacingOccurrences(of: #"\s*\(capital\)\s*$"#, with: "", options: .regularExpression))
    var aliases: Set<String> = [base]
    if base.hasPrefix("city of ") {
        let name = String(base.dropFirst(8)); aliases.insert(name); aliases.insert("\(name) city")
    }
    if base.hasSuffix(" city") {
        let name = String(base.dropLast(5)).trimmingCharacters(in: .whitespaces); aliases.insert(name); aliases.insert("city of \(name)")
    }
    let title = " \(norm(project["projectName"] as? String ?? "")) "
    return aliases.contains { !$0.isEmpty && title.contains(" \($0) ") }
}
func contains(_ lon: Double, _ lat: Double, _ rings: [[[Double]]]) -> Bool {
    var inside = false
    for ring in rings where ring.count > 2 {
        var hit = false
        var j = ring.count - 1
        for i in ring.indices {
            let a = ring[i], b = ring[j]
            if a.count >= 2 && b.count >= 2 && ((a[1] > lat) != (b[1] > lat)) && lon < (b[0] - a[0]) * (lat - a[1]) / (b[1] - a[1]) + a[0] { hit.toggle() }
            j = i
        }
        if hit { inside.toggle() }
    }
    return inside
}
func bounds(_ feature: [String: Any]) -> (minLon: Double, maxLon: Double, minLat: Double, maxLat: Double) {
    var result = (Double.infinity, -Double.infinity, Double.infinity, -Double.infinity)
    for ring in feature["rings"] as? [[[Double]]] ?? [] {
        for point in ring where point.count >= 2 {
            result.0 = min(result.0, point[0]); result.1 = max(result.1, point[0])
            result.2 = min(result.2, point[1]); result.3 = max(result.3, point[1])
        }
    }
    return result
}
func gap(_ a: (minLon: Double, maxLon: Double, minLat: Double, maxLat: Double), _ b: (minLon: Double, maxLon: Double, minLat: Double, maxLat: Double)) -> (Double, Double) {
    (max(0.0, max(a.minLon - b.maxLon, b.minLon - a.maxLon)), max(0.0, max(a.minLat - b.maxLat, b.minLat - a.maxLat)))
}
func localityFeatures(_ project: [String: Any], _ lat: Double, _ lon: Double, _ all: [[String: Any]]) -> (features: [[String: Any]], containing: [String: Any]?) {
    let containing = all.first { feature in contains(lon, lat, feature["rings"] as? [[[Double]]] ?? []) }
    let containingProvince = containing?["province"] as? String ?? ""
    let projectProvince = project["province"] as? String ?? ""
    let projectID = project["id"] as? String ?? ""
    let candidates = all.filter { feature in
        if containing != nil && !containingProvince.isEmpty { return norm(feature["province"] as? String ?? "") == norm(containingProvince) }
        let nearby = feature["nearbyProjectIds"] as? [String] ?? []
        return norm(feature["province"] as? String ?? "") == norm(projectProvince) || nearby.contains(projectID)
    }
    let pool = candidates.isEmpty ? all : candidates
    let anchor: [String: Any]? = containing ?? pool.min { a, b in
        let point = (minLon: lon, maxLon: lon, minLat: lat, maxLat: lat)
        let ga = gap(point, bounds(a)), gb = gap(point, bounds(b)), cosLat = cos(lat * Double.pi / 180)
        return hypot(ga.0 * cosLat, ga.1) < hypot(gb.0 * cosLat, gb.1)
    }
    guard let anchor else { return ([], containing) }
    let anchorBounds = bounds(anchor), limit = 0.035
    var neighbors = pool.filter { feature in
        guard (feature["key"] as? String) != (anchor["key"] as? String) else { return false }
        let g = gap(anchorBounds, bounds(feature)); return g.0 <= limit && g.1 <= limit
    }
    if neighbors.isEmpty {
        neighbors = pool.filter { ($0["key"] as? String) != (anchor["key"] as? String) }.sorted { a, b in
            let ga = gap(anchorBounds, bounds(a)), gb = gap(anchorBounds, bounds(b))
            return hypot(ga.0, ga.1) < hypot(gb.0, gb.1)
        }.prefix(1).map { $0 }
    }
    return ([anchor] + neighbors, containing)
}
let navy = color(0x00246A), panel = color(0x0038A8), pale = color(0xEAF0FF)
let muted = color(0xB9C9E8), blue = color(0x5B8DE8), red = color(0xCE1126), gold = color(0xFCD116)
let plot = NSRect(x: 580, y: 35, width: 590, height: 525)
for selected in projects {
    guard let slug = selected["shareSlug"] as? String,
          let lat = selected["latitude"] as? Double, let lon = selected["longitude"] as? Double else { continue }
    let image = NSImage(size: NSSize(width: width, height: height))
    image.lockFocus()
    navy.setFill(); NSBezierPath(rect: NSRect(x: 0, y: 0, width: width, height: height)).fill()
    let title = selected["projectName"] as? String ?? "Coordinate-bearing project"
    let office = selected["office"] as? String ?? "Office not stated"
    let raw = selected["coordinateRaw"] as? String ?? "Printed coordinate pair"
    let page = selected["sourcePage"] as? Int ?? 0
    let province = selected["province"] as? String ?? "Philippines"
    let facecards = selected["representativeCards"] as? [[String: Any]] ?? []
    let representative = facecards.first
    let representativeName = (representative?["name"] as? String) ?? (representative?["officialName"] as? String) ?? "Not resolved"
    let representativeDistrict = representative?["district"] as? String ?? "No geographic district match"
    panel.setFill()
    NSBezierPath(roundedRect: plot, xRadius: 18, yRadius: 18).fill()
    let namedFeatures = provinceFeatures.filter { isNamedIntended(selected, $0) }.sorted { a, b in
        let exactA = norm(a["province"] as? String ?? "") == norm(province)
        let exactB = norm(b["province"] as? String ?? "") == norm(province)
        if exactA != exactB { return exactA }
        return (featurePlace(a)?.count ?? 0) > (featurePlace(b)?.count ?? 0)
    }
    let intendedTarget = namedFeatures.first
    let intendedFeatures: [[String: Any]]
    if let intendedTarget {
        let intendedProvince = norm(intendedTarget["province"] as? String ?? "")
        let pool = provinceFeatures.filter { norm($0["province"] as? String ?? "") == intendedProvince }
        let anchorBounds = bounds(intendedTarget), limit = 0.035
        var adjacent = pool.filter { feature in
            guard (feature["key"] as? String) != (intendedTarget["key"] as? String) else { return false }
            let g = gap(anchorBounds, bounds(feature)); return g.0 <= limit && g.1 <= limit
        }
        if adjacent.isEmpty {
            adjacent = pool.filter { ($0["key"] as? String) != (intendedTarget["key"] as? String) }.sorted { a, b in
                let ga = gap(anchorBounds, bounds(a)), gb = gap(anchorBounds, bounds(b))
                return hypot(ga.0, ga.1) < hypot(gb.0, gb.1)
            }.prefix(1).map { $0 }
        }
        intendedFeatures = [intendedTarget] + adjacent
    } else {
        intendedFeatures = provinceFeatures.filter { norm($0["province"] as? String ?? "") == norm(province) }
    }
    let landing = localityFeatures(selected, lat, lon, provinceFeatures)
    var featureByKey: [String: [String: Any]] = [:]
    for feature in intendedFeatures + landing.features { featureByKey[feature["key"] as? String ?? UUID().uuidString] = feature }
    let features = Array(featureByKey.values)
    var minLon = lon, maxLon = lon, minLat = lat, maxLat = lat
    for feature in features {
        guard let rings = feature["rings"] as? [[[Double]]] else { continue }
        for ring in rings { for point in ring where point.count >= 2 {
            minLon = min(minLon, point[0]); maxLon = max(maxLon, point[0])
            minLat = min(minLat, point[1]); maxLat = max(maxLat, point[1])
        } }
    }
    let padLon = max(0.02, (maxLon - minLon) * 0.12), padLat = max(0.02, (maxLat - minLat) * 0.12)
    minLon -= padLon; maxLon += padLon; minLat -= padLat; maxLat += padLat
    let midLat = (minLat + maxLat) / 2, cosLat = max(0.2, cos(midLat * Double.pi / 180))
    let pad: CGFloat = 24
    let rangeX = max(0.002, (maxLon - minLon) * cosLat), rangeY = max(0.002, maxLat - minLat)
    let scale = min((plot.width - 2 * pad) / CGFloat(rangeX), (plot.height - 2 * pad) / CGFloat(rangeY))
    let usedW = CGFloat(rangeX) * scale, usedH = CGFloat(rangeY) * scale
    let left = plot.minX + (plot.width - usedW) / 2, bottom = plot.minY + (plot.height - usedH) / 2
    func mapPoint(_ pointLon: Double, _ pointLat: Double) -> NSPoint {
        NSPoint(x: left + CGFloat((pointLon - minLon) * cosLat) * scale,
                y: bottom + CGFloat(pointLat - minLat) * scale)
    }
    NSGraphicsContext.saveGraphicsState()
    NSBezierPath(rect: plot).addClip()
    for feature in features {
        guard let rings = feature["rings"] as? [[[Double]]] else { continue }
        let shape = NSBezierPath()
        for ring in rings where ring.count > 2 {
            guard let first = ring.first, first.count >= 2,
                  first[0] >= minLon - 0.4, first[0] <= maxLon + 0.4,
                  first[1] >= minLat - 0.4, first[1] <= maxLat + 0.4 else { continue }
            shape.move(to: mapPoint(first[0], first[1]))
            for pair in ring.dropFirst() where pair.count >= 2 { shape.line(to: mapPoint(pair[0], pair[1])) }
            shape.close()
        }
        shape.windingRule = .evenOdd
        let key = feature["key"] as? String ?? ""
        let intended = intendedTarget?["key"] as? String == key
        let landingArea = landing.containing?["key"] as? String == key
        let fill = intended && landingArea ? color(0xFCD116) : intended ? color(0xDBEAFE) : landingArea ? color(0xFCD116) : color(0xF5F5F5)
        let stroke = intended ? color(0x0038A8) : landingArea ? color(0xCE1126) : color(0xBDBDBD)
        fill.setFill()
        shape.fill()
        stroke.setStroke(); shape.lineWidth = intended || landingArea ? 1.2 : 0.65; shape.stroke()
    }
    let selectedPoint = mapPoint(lon, lat)
    let selectedDot = NSBezierPath(ovalIn: NSRect(x: selectedPoint.x - 8, y: selectedPoint.y - 8, width: 16, height: 16))
    red.setFill(); selectedDot.fill(); NSColor.white.setStroke(); selectedDot.lineWidth = 1.7; selectedDot.stroke()
    NSGraphicsContext.restoreGraphicsState()
    let intendedName = intendedTarget.flatMap { featurePlace($0) } ?? province
    let landingName = landing.containing.flatMap { featurePlace($0) } ?? "outside mapped boundary"
    text("Intended · \(intendedName)  /  Landing · \(landingName)", 600, 575, .boldSystemFont(ofSize: 13), pale)
    text("Blue · intended    Gold/red · coordinate landing    Gray · adjacent", 600, 15, .systemFont(ofSize: 11), muted)
    text("BETTERGOV.PH  /  FY2027 DPWH", 58, 566, .boldSystemFont(ofSize: 16), gold)
    text("Out of place?", 58, 502, .boldSystemFont(ofSize: 38), pale)
    for (line, value) in clippedLines(title, maxChars: 37, maxLines: 3).enumerated() {
        text(value, 60, 450 - CGFloat(line) * 34, .boldSystemFont(ofSize: 22), gold)
    }
    text(office, 60, 330, .systemFont(ofSize: 15), pale)
    text("Printed coordinate: \(raw)", 60, 294, .boldSystemFont(ofSize: 15), pale)
    text("HGAB 3rd PDF page \(page)", 60, 256, .systemFont(ofSize: 14), muted)
    text("Project-named province: \(province)", 60, 222, .systemFont(ofSize: 14), pale)
    text("Geographic representative", 148, 192, .systemFont(ofSize: 12), muted)
    text(representativeName, 148, 169, .boldSystemFont(ofSize: 14), pale)
    text(representativeDistrict, 148, 146, .systemFont(ofSize: 12), muted)
    if let portraitPath = portraitFiles[selected["id"] as? String ?? ""],
       let portrait = NSImage(contentsOfFile: portraitPath) {
        drawPortrait(portrait, in: NSRect(x: 60, y: 112, width: 70, height: 86))
    }
    text("A map review lead, not a finding", 60, 72, .systemFont(ofSize: 14), muted)
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    let png = bitmap.representation(using: .png, properties: [:])!
    try png.write(to: output.appendingPathComponent("\(slug).png"), options: .atomic)
}
