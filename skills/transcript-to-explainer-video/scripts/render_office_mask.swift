// Render a person matte for the 360x260 presenter window on macOS.
// Usage: render_office_mask SOURCE.mov START_SECONDS DURATION_SECONDS OUTPUT.mkv
// The output is 360x260, 30 fps, grayscale FFV1: 255=presenter, 0=background.

import AppKit
import CoreImage
import CoreVideo
import Foundation
import Vision

guard CommandLine.arguments.count == 5 else {
    fputs("usage: render_office_mask SOURCE.mov START DURATION OUTPUT.mkv\n", stderr)
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
let width = 360
let height = 260
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
    "-vf", "fps=30,scale=360:260:force_original_aspect_ratio=increase:flags=lanczos,crop=360:260",
    "-f", "rawvideo", "-pix_fmt", "bgra", "pipe:1",
], input: nil, output: decoderOut)
decoderOut.fileHandleForWriting.closeFile()

var encoderIn: Pipe? = nil
var encoder: Process? = nil
var expectedMaskWidth = 0
var expectedMaskHeight = 0

let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .balanced
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
            "-f", "rawvideo", "-pix_fmt", "gray", "-s", "\(maskWidth)x\(maskHeight)", "-r", "30",
            "-i", "pipe:0", "-an",
            "-vf", "scale=360:260:flags=bicubic",
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
        fputs(String(format: "frames=%d video=%.1fs wall=%.1fs\n", count, Double(count)/30, elapsed), stderr)
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
print(String(format: "Done: %d frames at 30 fps; wall %.2fs; output %@", count, elapsed, output))
