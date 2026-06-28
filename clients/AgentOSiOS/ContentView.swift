import SwiftUI

struct Msg: Identifiable {
    let id = UUID()
    let role: String      // "user" | "assistant"
    let text: String
}

struct ContentView: View {
    @EnvironmentObject var kernel: PythonKernel
    @State private var input = ""
    @State private var messages: [Msg] = []
    @State private var busy = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if !kernel.ready {
                    ProgressView("Starting Skipper…")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 10) {
                            if messages.isEmpty {
                                Text("Say hi to Skipper 👋")
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .center)
                                    .padding(.top, 60)
                            }
                            ForEach(messages) { m in
                                Text(m.text)
                                    .padding(10)
                                    .background(m.role == "user" ? Color.accentColor.opacity(0.15)
                                                                 : Color.gray.opacity(0.12))
                                    .clipShape(RoundedRectangle(cornerRadius: 12))
                                    .frame(maxWidth: .infinity,
                                           alignment: m.role == "user" ? .trailing : .leading)
                            }
                        }
                        .padding()
                    }
                    HStack(spacing: 8) {
                        TextField("Message Skipper…", text: $input, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                        Button { send() } label: {
                            Image(systemName: "arrow.up.circle.fill").font(.title2)
                        }
                        .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || busy)
                    }
                    .padding()
                }
            }
            .background(Color(.systemBackground))
            .navigationTitle("Skipper")
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        messages.append(Msg(role: "user", text: text))
        input = ""
        busy = true
        Task {
            // NOTE: for real Gemma this should move off the main actor — see IOS_BUILD.md §4.
            let reply = kernel.send(text)
            messages.append(Msg(role: "assistant", text: reply))
            busy = false
        }
    }
}
