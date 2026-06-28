import SwiftUI
import AgentOSKit

/// Sidebar: the live agent list from GET /agents, plus a connection indicator.
struct AgentPickerView: View {
    @ObservedObject var vm: ChatViewModel

    var body: some View {
        List(selection: Binding(
            get: { vm.selectedAgentName },
            set: { if let v = $0 { vm.selectedAgentName = v } }
        )) {
            Section("Agents") {
                ForEach(vm.agents) { agent in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(agent.title)
                        if let model = agent.model {
                            Text(model).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .tag(agent.name)
                }
                if vm.agents.isEmpty {
                    Text("No agents — is the kernel running?")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .safeAreaInset(edge: .bottom) { connectionBar }
    }

    private var connectionBar: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(vm.health != nil ? Color.green : Color.red)
                .frame(width: 8, height: 8)
            Text(vm.health != nil ? "Connected · v\(vm.health!.version)" : "Offline")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button {
                Task { await vm.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Refresh")
        }
        .padding(8)
        .background(.bar)
    }
}
