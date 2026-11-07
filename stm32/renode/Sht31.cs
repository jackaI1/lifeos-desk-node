using Antmicro.Renode.Peripherals.I2C;
namespace Antmicro.Renode.Peripherals.Sensors
{
 public class DeskSht31 : II2CPeripheral
 {
  // STM32F4_I2C requests the whole transaction with Read(), whose optional
  // count defaults to one. Supply the complete six-byte protocol response.
  public byte[] Read(int count=1) {
   var result=ready ? (byte[])sample.Clone() : new byte[6];
   if(Corrupt)result[2]^=1;
   ready=false;
   return result;
  }
  public void Write(byte[] data) { ready=data.Length==2 && data[0]==0x24 && data[1]==0x00; }
  public void FinishTransmission() { }
  public void Reset() { ready=false;Corrupt=false; }
  public bool Corrupt { get; set; }
  private bool ready;
  private readonly byte[] sample={0x66,0x66,0x93,0x80,0x00,0xa2};
 }
}
