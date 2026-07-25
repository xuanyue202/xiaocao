#!/usr/bin/env swift

import AppKit
import Foundation
import Vision

struct OcrLine: Codable {
    let text: String
    let confidence: Float
    let bounding_box: [CGFloat]
}

struct OcrResult: Codable {
    let engine: String
    let lines: [OcrLine]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

guard CommandLine.arguments.count == 2 else {
    fail("usage: kol_vision_ocr.swift <image>")
}

let imageUrl = URL(fileURLWithPath: CommandLine.arguments[1])
guard
    let image = NSImage(contentsOf: imageUrl),
    let imageData = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: imageData),
    let cgImage = bitmap.cgImage
else {
    fail("image could not be decoded")
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true

do {
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
} catch {
    fail("Vision OCR request failed")
}

let observations = request.results ?? []
let lines = observations.compactMap { observation -> OcrLine? in
    guard let candidate = observation.topCandidates(1).first else {
        return nil
    }
    let box = observation.boundingBox
    return OcrLine(
        text: candidate.string,
        confidence: candidate.confidence,
        bounding_box: [box.origin.x, box.origin.y, box.size.width, box.size.height]
    )
}

guard !lines.isEmpty else {
    fail("Vision OCR produced no text")
}

do {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(
        OcrResult(engine: "macos_vision", lines: lines)
    ))
} catch {
    fail("OCR JSON encoding failed")
}
