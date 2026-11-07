using System;
using System.IO;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
public static class ClampReadback {
 static void Save(IModelDoc2 m,string path){int e=0,w=0;if(!m.Extension.SaveAs(path,0,1,null,ref e,ref w)||e!=0)throw new Exception("Readback save failed "+e);}
 public static void Run(string root,bool drawing){
  if(File.Exists(Path.Combine(root,"manifest.csv")))throw new Exception("Released folder protected. Copy to scratch for readback.");
  ISldWorks sw=(ISldWorks)Activator.CreateInstance(Type.GetTypeFromProgID("SldWorks.Application"));sw.Visible=true;
  if(sw.GetDocumentCount()!=0)throw new Exception("Existing documents protected on reopen");
  int e=0,w=0;IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(Path.Combine(root,"CL-000_clamp.SLDASM"),2,1,"",ref e,ref w);
  if(m==null||e!=0)throw new Exception("Assembly reopen failed "+e);
  IAssemblyDoc ass=(IAssemblyDoc)m;bool rebuilt=m.ForceRebuild3(false);int refs=0,floating=0;var components=new List<object>();
  foreach(IComponent2 c in (object[])ass.GetComponents(false)){
   if(c.GetModelDoc2()==null)throw new Exception("Unresolved component "+c.Name2);
   string expectedRoot=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar;
   if(!c.GetPathName().StartsWith(expectedRoot,StringComparison.OrdinalIgnoreCase))throw new Exception("Component resolved outside case folder");

   object[] mates=(object[])c.GetMates();int count=mates==null?0:mates.Length;refs+=count;
   if(!c.IsFixed()){floating++;if(count!=3)throw new Exception("Expected three mates on "+c.Name2);}
   components.Add(new {component=c.Name2,part=Path.GetFileName(c.GetPathName()),fixed_component=c.IsFixed(),mate_references=count,transform=(double[])c.Transform2.ArrayData});
  }
  IInterferenceDetectionMgr manager=(IInterferenceDetectionMgr)ass.InterferenceDetectionManager;manager.TreatCoincidenceAsInterference=false;
  object[] hits=(object[])manager.GetInterferences();int interferences=hits==null?0:hits.Length;
  foreach(IComponent2 c in (object[])ass.GetComponents(false)){
   int pe=0,pw=0;((IModelDoc2)c.GetModelDoc2()).Save3(1,ref pe,ref pw);if(pe!=0)throw new Exception("Referenced part save failed "+pe);
  }
  int saveErrors=0,saveWarnings=0;m.Save3(1,ref saveErrors,ref saveWarnings);if(saveErrors!=0)throw new Exception("Rebuilt assembly save failed "+saveErrors);
  File.WriteAllText(Path.Combine(root,"reopen-check.json"),new JavaScriptSerializer().Serialize(new {rebuild=rebuilt,open_errors=e,open_warnings=w,open_warning_name=((swFileLoadWarning_e)w).ToString(),save_errors=saveErrors,save_warnings=saveWarnings,components=components,component_count=ass.GetComponentCount(false),floating_components=floating,mate_references=refs,mates=refs/2,interferences=interferences}));
  if(!rebuilt||interferences!=0||refs!=48||floating!=8)throw new Exception("Reopen validation failed");
  if(drawing){
   string template=Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.ProgramFiles),"SOLIDWORKS Corp","SOLIDWORKS","data","templates","iso.drwdot");
   IModelDoc2 sheet=(IModelDoc2)sw.NewDocument(template,12,.420,.297);
   IDrawingDoc d=(IDrawingDoc)sheet;d.SetupSheet5("Sheet1",12,12,1,1,false,"",.420,.297,"Default",true);
   sheet.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swUnitsLinear,(int)swLengthUnit_e.swMM);
   d.CreateDrawViewFromModelView3(m.GetPathName(),"*Top",.105,.19,0);d.CreateDrawViewFromModelView3(m.GetPathName(),"*Isometric",.285,.19,0);
   sheet.ClearSelection2(true);
   INote n=(INote)sheet.InsertNote("CL-000 CLAMP ASSEMBLY | Student Edition prototype\nDimensions mm. See individual tolerance drawings and bom.csv.\n1 base, 3 locator pins, 1 arm, 1 reference coupon, 1 M5 reference bolt, washer and square nut.\n24 native plane mates; zero static interference on reopen. Intended contacts coincide.\nMount base on spacers for underside nut access. No thread engagement or load rating modeled.\nMaterials: 6061 base and arm; steel pins and fasteners; PETG reference coupon.\nNo physical assembly or clamping test. Confirm actual hardware and inspect fit before use.");
   ((IAnnotation)n.GetAnnotation()).SetPosition2(.055,.08,0);sheet.ViewZoomtofit2();
   foreach(string ext in new[]{"SLDDRW","pdf","png"})Save(sheet,Path.Combine(root,"CL-000_clamp-drawing."+ext));
   sw.CloseDoc(sheet.GetTitle());
  }
  sw.CloseDoc(m.GetTitle());sw.ExitApp();
 }
}
