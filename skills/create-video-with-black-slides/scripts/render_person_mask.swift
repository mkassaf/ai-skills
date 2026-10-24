// Render a full-frame person matte against black on macOS.
// Usage: render_person_mask SOURCE.mov START_SECONDS DURATION_SECONDS OUTPUT.mkv [WIDTH HEIGHT FPS]
// Default output: 1280x720/30fps grayscale FFV1, 255=presenter, 0=background.

import AppKit
import CoreImage
import CoreVideo
import Foundation
import Vision

guard [5, 8].contains(CommandLine.arguments.count) else {
    fputs("usage: render_person_mask SOURCE.mov START DURATION OUTPUT.mkv [WIDTH HEIGHT FPS]\n", stderr)
    exit(2)
}

func locateFFmpeg() -> String {
    let fm = FileManager.default
    if let override = ProcessInfo.processInfo.environment["FFMPEG"],
       fm.isExecutableFile(atPath: override) {
        return override
    }
    let path = ProcessInfo.processInfo.environment["PATH"] ?? ""
    for directory in path.split(separator: ":") {
        let candidate = String(directory) + "/ffmpeg"
        if fm.isExecutableFile(atPath: candidate) { return candidate }
    }
    let fallback = "/Applications/Weline Pro.app/Contents/Resources/mac_pc_nas/ffmpeg"
    if fm.isExecutableFile(atPath: fallback) { return fallback }
    fatalError("FFmpeg is required. Put it on PATH or set FFMPEG=/path/to/ffmpeg")
}

let ffmpeg = locateFFmpeg()
let source = CommandLine.arguments[1]
let start = CommandLine.arguments[2]
let duration = CommandLine.arguments[3]
let output = CommandLine.arguments[4]
let outputWidth = CommandLine.arguments.count == 8 ? (Int(CommandLine.arguments[5]) ?? 0) : 1280
let outputHeight = CommandLine.arguments.count == 8 ? (Int(CommandLine.arguments[6]) ?? 0) : 720
let fps = CommandLine.arguments.count == 8 ? (Int(CommandLine.arguments[7]) ?? 0) : 30
guard outputWidth > 0, outputHeight > 0, outputWidth % 2 == 0, outputHeight % 2 == 0, fps > 0,
      let durationValue = Double(duration), durationValue > 0,
      let startValue = Double(start), startValue >= 0 else { fatalError("Invalid dimensions, fps, start, or duration") }
guard URL(fileURLWithPath: source).standardizedFileURL != URL(fileURLWithPath: output).standardizedFileURL else { fatalError("Output must differ from source") }
try FileManager.default.createDirectory(at: URL(fileURLWithPath: output).deletingLastPathComponent(), withIntermediateDirectories: true)
let width = 640
let height = max(32, Int((Double(outputHeight) * 640.0 / Double(outputWidth) / 2.0).rounded()) * 2)
let rawFrameBytes = width * height * 4

func command(_ args: [String], input: Pipe?, output: Pipe?) throws -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: ffmpeg)
    process.arguments = args
    if let input { process.standardInput = input }
    if let output { process.standardOutput = output }
    process.standardError = FileHandle.standardError
    try process.run()
    return process
}

func readExact(_ handle: FileHandle, count: Int) -> Data? {
    var result = Data()
    while result.count < count {
        let chunk = handle.readData(ofLength: count - result.count)
        if chunk.isEmpty {
            if result.isEmpty { return nil }
            fatalError("Decoder returned a partial video frame")
        }
        result.append(chunk)
    }
    return result
}

let decoderOut = Pipe()
let decoder = try command([
    "-hide_banner", "-loglevel", "error", "-ss", start, "-i", source,
    "-t", duration, "-an",
    "-vf", "fps=\(fps),scale=\(outputWidth):\(outputHeight):force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos,pad=\(outputWidth):\(outputHeight):(ow-iw)/2:(oh-ih)/2,scale=\(width):\(height):flags=lanczos",
    "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1",
], input: nil, output: decoderOut)
decoderOut.fileHandleForWriting.closeFile()

var encoderIn: Pipe? = nil
var encoder: Process? = nil
var expectedMaskWidth = 0
var expectedMaskHeight = 0

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8
let colorSpace = CGColorSpaceCreateDeviceRGB()
let startTime = CFAbsoluteTimeGetCurrent()
var count = 0

while let bytes = readExact(decoderOut.fileHandleForReading, count: rawFrameBytes) {
    let image = CIImage(
        bitmapData: bytes,
        bytesPerRow: width * 4,
        size: CGSize(width: width, height: height),
        format: .BGRA8,
        colorSpace: colorSpace
    )
    try VNImageRequestHandler(ciImage: image, options: [:]).perform([request])
    guard let mask = request.results?.first?.pixelBuffer else {
        fatalError("Vision produced no person mask at frame \(count)")
    }
    let maskWidth = CVPixelBufferGetWidth(mask)
    let maskHeight = CVPixelBufferGetHeight(mask)
    if encoder == nil {
        expectedMaskWidth = maskWidth
        expectedMaskHeight = maskHeight
        let pipe = Pipe()
        let process = try command([
            "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "gray", "-s", "\(maskWidth)x\(maskHeight)", "-r", String(fps),
            "-i", "pipe:0", "-an",
            "-vf", "scale=\(outputWidth):\(outputHeight):flags=bicubic,erosion,gblur=sigma=0.55",
            "-c:v", "ffv1", "-pix_fmt", "gray", output,
        ], input: pipe, output: nil)
        pipe.fileHandleForReading.closeFile()
        encoderIn = pipe
        encoder = process
    } else if maskWidth != expectedMaskWidth || maskHeight != expectedMaskHeight {
        fatalError("Vision mask dimensions changed between frames")
    }
    CVPixelBufferLockBaseAddress(mask, .readOnly)
    guard let base = CVPixelBufferGetBaseAddress(mask) else { fatalError("No mask bytes") }
    let stride = CVPixelBufferGetBytesPerRow(mask)
    var packed = Data(count: maskWidth * maskHeight)
    packed.withUnsafeMutableBytes { dest in
        guard let destBase = dest.baseAddress else { return }
        for y in 0..<maskHeight {
            memcpy(destBase.advanced(by: y * maskWidth), base.advanced(by: y * stride), maskWidth)
        }
    }
    CVPixelBufferUnlockBaseAddress(mask, .readOnly)
    encoderIn!.fileHandleForWriting.write(packed)
    count += 1
    if count % 90 == 0 {
        let elapsed = CFAbsoluteTimeGetCurrent() - startTime
        fputs(String(format: "frames=%d video=%.1fs wall=%.1fs\n", count, Double(count)/Double(fps), elapsed), stderr)
    }
}

decoderOut.fileHandleForReading.closeFile()
decoder.waitUntilExit()
guard count > 0, let encoderIn, let encoder else {
    fatalError("No input video frames were decoded")
}
encoderIn.fileHandleForWriting.closeFile()
encoder.waitUntilExit()
guard decoder.terminationStatus == 0 && encoder.terminationStatus == 0 else {
    fatalError("ffmpeg decoder=\(decoder.terminationStatus) encoder=\(encoder.terminationStatus)")
}
let elapsed = CFAbsoluteTimeGetCurrent() - startTime
print(String(format: "Done: %d frames; wall %.2fs; output %@", count, elapsed, output))
