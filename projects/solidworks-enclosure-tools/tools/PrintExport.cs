using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
public static class PrintExport {
 public static void Run(string source,string output) {
  Directory.CreateDirectory(output);
  ISldWorks sw=(ISldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application"));
  sw.Visible=true;
  if(sw.GetDocumentCount()!=0)throw new Exception("Existing documents protected. Close them before exporting.");
  using(var log=new StreamWriter(Path.Combine(output,"solidworks-export.txt"))) {
   log.AutoFlush=true;log.WriteLine("SolidWorks "+sw.RevisionNumber()+" Student Edition; exported from native revision A.");
   foreach(string id in new[]{"ED-001_case_A","ED-002_lid_A"}) {
    int e=0,w=0;IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(Path.Combine(source,id+".SLDPRT"),1,1,"",ref e,ref w);
    if(m==null)throw new Exception("Open failed "+id+" error "+e);
    try {
     bool rebuilt=m.ForceRebuild3(false);if(!rebuilt)throw new Exception("Rebuild failed "+id);
     IPartDoc part=(IPartDoc)m;object[] bodies=(object[])part.GetBodies2(0,false);
     double volume=0;foreach(IBody2 b in bodies){if(b.Check()!=1)throw new Exception("Invalid body");volume+=((double[])b.GetMassProperties(1))[3]*1e9;}
     bool ok=m.Extension.SaveAs(Path.Combine(output,id+".stl"),0,1,null,ref e,ref w);
     if(!ok||e!=0)throw new Exception("STL export failed "+e);
     log.WriteLine(id+" rebuilt="+rebuilt+" bodies="+bodies.Length+" volume_mm3="+volume+" STL_errors="+e+" warnings="+w);
    } finally {sw.CloseDoc(m.GetTitle());}
   }
  }
  sw.ExitApp();
 }
}
