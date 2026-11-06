using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
public static class Readback {
 public static void Run(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  foreach(IModelDoc2 m in (object[])sw.GetDocuments()) {
   string path=m.GetPathName();if(path.StartsWith(Directory.GetParent(Directory.GetParent(root).FullName).FullName,StringComparison.OrdinalIgnoreCase))sw.CloseDoc(m.GetTitle());
  }
  using(var log=new StreamWriter(Path.Combine(root,"final-readback.txt"))) {
   foreach(string path in Directory.GetFiles(root,"*.SLDPRT")) {
    if(Path.GetFileName(path).StartsWith("~$"))continue;int e=0,w=0;
    IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(path,1,1,"",ref e,ref w);
    if(m==null||e!=0||!m.ForceRebuild3(false))throw new Exception("Reopen/rebuild failed");
    object[] bs=(object[])((IPartDoc)m).GetBodies2(0,false);if(bs.Length!=1)throw new Exception("Unexpected body count");
    log.WriteLine("REOPEN "+Path.GetFileName(path)+" errors="+e+" warnings="+w+" rebuild=True bodies="+bs.Length);
   }
   int er=0,wr=0;IModelDoc2 ass=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"ED-000_desk_device_A.SLDASM"),2,1,"",ref er,ref wr);
   sw.ActivateDoc3(ass.GetTitle(),false,0,ref er);
   foreach(string config in (string[])ass.GetConfigurationNames()) {
    ass.ShowConfiguration2(config);if(!ass.ForceRebuild3(false))throw new Exception("Assembly rebuild failed");
    log.WriteLine("CONFIG "+config);
    foreach(IComponent2 c in (object[])((IAssemblyDoc)ass).GetComponents(false)) {
     if(c.IsSuppressed())continue;
     if(c.GetModelDoc2()==null||!File.Exists(c.GetPathName()))throw new Exception("Unresolved reference");
     if(c.GetPathName().EndsWith("ED-003_hatch_A.SLDPRT",StringComparison.OrdinalIgnoreCase)) {
      double[] a=(double[])c.Transform2.ArrayData;bool open=config=="Hatch_open_90";
      log.WriteLine("ACTUAL_HATCH_POSE "+string.Join(",",a));
      if(Math.Abs(a[0]-(open?0:1))>1e-7||Math.Abs(a[11]-.0387)>1e-7)throw new Exception("Saved hatch pose mismatch");
      log.WriteLine("SAVED_HATCH_POSE "+string.Join(",",a));
     }
    }
   }
   ass.ShowConfiguration2("Default");ass.ShowNamedView2("*Isometric",7);ass.ViewZoomtofit2();
  }
 }
}
