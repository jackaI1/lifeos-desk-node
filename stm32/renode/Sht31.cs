using Antmicro.Renode.Peripherals.I2C;
namespace Antmicro.Renode.Peripherals.Sensors
{
 public class DeskSht31 : II2CPeripheral
 {
  public byte[] Read(int count=1) { var result=new byte[count]; for(int i=0;i<count;i++)result[i]=sample[(position++)%6];return result; }
  public void Write(byte[] data) { position=0; }
  public void FinishTransmission() { position=0; }
  public void Reset() { position=0; }
  private int position;
  private readonly byte[] sample={0x66,0x66,0x93,0x80,0x00,0xa2};
 }
}
