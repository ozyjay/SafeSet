import CryptoKit
import Foundation

enum DevelopmentPassphrase {
    #if DEBUG
    private static let fixtureDigests: Set<String> = [
        "36aca5b86f05eb98a63eb571c3a85483453cdee16f78c06c5c7e9e42bfff1158",
        "3862bcb6ce3cab1bee12d0c8bc75db0fc53b15aacb47832724b6edae1f3ef5bd"
    ]

    static func forWorkbook(_ path: String) -> String? {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: path),
              let size = attributes[.size] as? Int,
              size <= 10 * 1024 * 1024,
              let data = try? Data(contentsOf: URL(fileURLWithPath: path), options: .mappedIfSafe)
        else { return nil }
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return fixtureDigests.contains(digest)
            ? "SafeSet-Debug-Synthetic-Fixture-Only-2026" : nil
    }
    #else
    static func forWorkbook(_ path: String) -> String? { nil }
    #endif
}
