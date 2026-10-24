import AppKit
let root=URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1200,pixelsHigh:1600,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:4800,bitsPerPixel:32)!
NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:rep)
NSColor.white.setFill();NSRect(x:0,y:0,width:1200,height:1600).fill()
let art=NSImage(contentsOf:root.appendingPathComponent("painting/v2-ae36dd9cc63c5c071cd9611976aff2e9_r.jpg"))!
art.draw(in:NSRect(x:0,y:580,width:1200,height:1020),from:NSRect(x:8,y:(art.size.height-(art.size.width-16)*1020/1200)/2,width:art.size.width-16,height:(art.size.width-16)*1020/1200),operation:.copy,fraction:1)
func text(_ s:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ bold:Bool=false){
let font=bold ? NSFont.boldSystemFont(ofSize:size) : NSFont.systemFont(ofSize:size)
(s as NSString).draw(at:NSPoint(x:x,y:y),withAttributes:[.font:font,.foregroundColor:NSColor.black])}
text("Stillframe",52,506,46,true);text("让喜欢的画，留在眼前",52,436,52,true)
text("首次使用 · 两步完成设置",52,367,32,true)
text("1  打开手机 Wi-Fi，连接 Stillframe",52,309,30)
text("    密码：12345678",52,264,30)
text("2  连接后扫描右侧二维码",52,201,30)
text("    设置家庭 Wi-Fi 和相册服务器",52,157,30)
text("    或打开 http://192.168.4.1",52,113,28)
text("    网页登录：admin / 12345678",52,72,28)
text("如提示无互联网，请选择保持连接。",52,27,24)
let qr=NSImage(contentsOf:root.appendingPathComponent("simulator/public/assets/setup-qr.png"))!
NSGraphicsContext.current!.imageInterpolation = .none
qr.draw(in:NSRect(x:876,y:128,width:264,height:264))
NSGraphicsContext.restoreGraphicsState()
try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("firmware/assets/setup.png"))
