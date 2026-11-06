using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
public static class AssemblyCheck {
 public static void Run(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");int e=0,w=0;
  IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"ED-000_desk_device_A.SLDASM"),2,1,"",ref e,ref w);
  sw.ActivateDoc3(m.GetTitle(),false,0,ref e);
  HatchStates.Setup(m,sw);
  using(var log=new StreamWriter(Path.Combine(root,"assembly-check.txt"))) {
   foreach(string config in (string[])m.GetConfigurationNames()) {
    log.WriteLine("SELECT "+config+" active="+m.ConfigurationManager.ActiveConfiguration.Name);
    if(m.ConfigurationManager.ActiveConfiguration.Name!=config && !m.ShowConfiguration2(config))throw new Exception("Configuration failed: "+config);
    foreach(IComponent2 c in (object[])((IAssemblyDoc)m).GetComponents(false))if(!c.IsSuppressed()&&c.GetPathName().EndsWith("ED-003_hatch_A.SLDPRT",StringComparison.OrdinalIgnoreCase)) {
     log.WriteLine("HATCH_TRANSFORM "+string.Join(",",(double[])c.Transform2.ArrayData));
    }
    log.WriteLine("CONFIG "+config+" rebuild="+m.ForceRebuild3(false));
    IInterferenceDetectionMgr interference=(IInterferenceDetectionMgr)((IAssemblyDoc)m).InterferenceDetectionManager;
    interference.TreatCoincidenceAsInterference=false;
    object[] hits=(object[])interference.GetInterferences();
    log.WriteLine("INTERFERENCES "+(hits==null?0:hits.Length));
    if(hits!=null)foreach(IInterference hit in hits){log.WriteLine("OVERLAP_MM3 "+hit.Volume*1e9);foreach(IComponent2 c in (object[])hit.Components)log.WriteLine("OVERLAP_PART "+Path.GetFileName(c.GetPathName()));}
    foreach(IComponent2 c in (object[])((IAssemblyDoc)m).GetComponents(false)) {
     if(c.IsSuppressed())continue;
     string path=c.GetPathName();bool exists=File.Exists(path),resolved=c.GetModelDoc2()!=null;
     log.WriteLine("COMPONENT "+Path.GetFileName(path)+" exists="+exists+" resolved="+resolved);
     if(!exists||!resolved)throw new Exception("Unresolved reference");
    }
    m.ShowNamedView2("*Isometric",7);m.ViewZoomtofit2();
    m.SaveAs3(Path.Combine(root,config=="Default"?"assembly.png":"assembly-open.png"),0,1);
    m.Save3(1,ref e,ref w);
   }
   m.ShowConfiguration2("Default");m.Save3(1,ref e,ref w);log.WriteLine("SAVE errors="+e+" warnings="+w);
  }
 }
}
