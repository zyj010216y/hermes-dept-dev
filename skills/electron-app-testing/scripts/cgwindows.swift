// cgwindows.swift — 枚举 macOS 全部窗口（含隐藏/置顶/离屏），可按 owner 子串过滤
// 用法: swift cgwindows.swift [ownerSubstring]   (省略参数则列出全部窗口)
// 适用: cua-driver list_windows 漏掉 layer 1001 浮动窗/隐藏窗/off-screen 窗时
import CoreGraphics
import Foundation

let filter = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : nil
let wl = CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]] ?? []
for w in wl {
    let owner = w[kCGWindowOwnerName as String] as? String ?? "?"
    if let f = filter, !owner.contains(f) { continue }
    let num = w[kCGWindowNumber as String] ?? "?"
    let layer = w[kCGWindowLayer as String] ?? "?"
    let onscreen = w[kCGWindowIsOnscreen as String] ?? "?"
    let alpha = w[kCGWindowAlpha as String] ?? "?"
    let name = w[kCGWindowName as String] as? String ?? ""
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    print("winNum:\(num) layer:\(layer) onscreen:\(onscreen) alpha:\(alpha) name:\(name) bounds:\(b)")
}
