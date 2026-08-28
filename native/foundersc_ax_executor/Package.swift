// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FounderscNativeAX",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "foundersc-native-ax", targets: ["FounderscNativeAX"]),
    ],
    targets: [
        .executableTarget(name: "FounderscNativeAX"),
    ]
)
