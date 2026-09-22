// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "SafeSetMac",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "SafeSetMac", targets: ["SafeSetMac"])],
    targets: [
        .executableTarget(name: "SafeSetMac", path: "Sources"),
        .testTarget(name: "SafeSetMacTests", dependencies: ["SafeSetMac"], path: "Tests")
    ]
)
