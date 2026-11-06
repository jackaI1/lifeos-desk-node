using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
public static class DrawingDetails {
 public static void Run(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  foreach(string id in new[]{"ED-001_case_A","ED-002_lid_A"}) {
   int e=0,w=0;IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,id+".SLDDRW"),3,1,"",ref e,ref w);
   int a=0;sw.ActivateDoc3(m.GetTitle(),false,0,ref a);m.ClearSelection2(true);
   IGtol g=(IGtol)m.InsertGtol();g.SetFrameSymbols2(1,"<IGTOL-FLAT>",false,"",false,"","","","");g.SetFrameValues(1,"0.30","","","","");
   ((IAnnotation)g.GetAnnotation()).SetPosition2(.21,.045,0);
   m.ClearSelection2(true);INote n=(INote)m.InsertNote("Flatness applies to datum face A identified above.\nGeneral tolerance is a design target. Print a fit coupon first.");
   ((IAnnotation)n.GetAnnotation()).SetPosition2(.21,.032,0);
   m.Save3(1,ref e,ref w);if(e!=0)throw new Exception("Drawing save "+e);
   if(m.SaveAs3(Path.Combine(root,id+".pdf"),0,1)!=0)throw new Exception("PDF export failed");
  }
 }
}
