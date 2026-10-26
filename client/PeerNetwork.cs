using System;
using System.Threading.Tasks;

namespace CampusLink.Client {
    public interface IPacketTransport : IDisposable {
        Func<byte[],Task> Packet { get; set; }
        Action<string> Ended { get; set; }
        Action<string> Changed { get; set; }
        string Name { get; }
        Task Send(byte[] packet);
        Task Ready(bool initiate);
    }
    public interface IPeerNetwork : IDisposable {
        Action<string> Status { get; set; }
        Action<ClientSession> Incoming { get; set; }
        string Invitation { get; }
        string DeviceId { get; }
        Task Join(string code);
        Task<ClientSession> Connect(string code);
    }
}
