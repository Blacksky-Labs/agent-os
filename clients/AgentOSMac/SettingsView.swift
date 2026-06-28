import SwiftUI

struct SettingsView: View {
    @ObservedObject var vm: ChatViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Form {
                Section("Kernel") {
                    TextField("Base URL", text: $vm.baseURLString)
                    TextField("User ID", text: $vm.userId)
                }
                Section {
                    Text("Skipper runs locally. Start the kernel with `agentos start skipper`. Default base URL is http://127.0.0.1:1776.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)

            HStack {
                Button("Clear conversation", role: .destructive) {
                    vm.clearTranscript()
                }
                Spacer()
                Button("Cancel") { dismiss() }
                Button("Apply") {
                    vm.applySettings()
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
            }
            .padding()
        }
        .frame(width: 460)
    }
}
