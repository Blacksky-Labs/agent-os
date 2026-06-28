import SwiftUI
import AgentOSKit

struct ChatView: View {
    @ObservedObject var vm: ChatViewModel

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if vm.messages.isEmpty {
                            Text("Talk to Skipper. It keeps what matters and brings it back when it counts.")
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.top, 60)
                        }
                        ForEach(vm.messages) { msg in
                            MessageRow(message: msg).id(msg.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: vm.messages.count) { _ in
                    if let last = vm.messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
            }
            Divider()
            composer
        }
        .navigationTitle(currentTitle)
    }

    private var currentTitle: String {
        vm.agents.first(where: { $0.name == vm.selectedAgentName })?.title ?? "Skipper"
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Talk to Skipper…", text: $vm.input, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...5)
                .onSubmit { Task { await vm.send() } }
            Button {
                Task { await vm.send() }
            } label: {
                if vm.isSending {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "arrow.up.circle.fill").font(.title2)
                }
            }
            .buttonStyle(.plain)
            .disabled(vm.isSending || vm.input.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding()
    }
}

struct MessageRow: View {
    let message: Message

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 40) }
            Text(message.text)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(background)
                .foregroundStyle(foreground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            if message.role != .user { Spacer(minLength: 40) }
        }
    }

    private var background: Color {
        switch message.role {
        case .user: return .accentColor
        case .assistant: return Color(nsColor: .controlBackgroundColor)
        case .system: return Color.orange.opacity(0.18)
        }
    }

    private var foreground: Color {
        message.role == .user ? .white : .primary
    }
}
