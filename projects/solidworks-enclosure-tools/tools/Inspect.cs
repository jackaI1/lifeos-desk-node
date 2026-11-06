using System;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.cosworks;
public static class Inspect {
 public static void Run(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
  foreach(IModelDoc2 open in (object[])sw.GetDocuments()) {
   if(open.GetPathName().StartsWith(root,StringComparison.OrdinalIgnoreCase)) sw.CloseDoc(open.GetTitle());
  }
  using(var log=new StreamWriter(Path.Combine(root,"inspection.txt"))) {
   log.AutoFlush=true;
   foreach(string path in Directory.GetFiles(root,"*.SLDPRT")) {
    if(Path.GetFileName(path).StartsWith("~$"))continue;
    int e=0,w=0;IModelDoc2 m=(IModelDoc2)sw.OpenDoc6(path,1,1,"",ref e,ref w);
    if(m==null)throw new Exception("Reopen failed "+Path.GetFileName(path));
    bool rebuilt=m.ForceRebuild3(false);object[] bodies=(object[])((IPartDoc)m).GetBodies2(0,false);
    log.WriteLine("REOPEN "+Path.GetFileName(path)+" errors="+e+" warnings="+w+" rebuild="+rebuilt+" bodies="+bodies.Length);
    foreach(IBody2 b in bodies)log.WriteLine("BOX_MM "+string.Join(",",Array.ConvertAll((double[])b.GetBodyBox(),v=>(v*1000).ToString("F3"))));
   }
   int err=0;IModelDoc2 lid=(IModelDoc2)sw.ActivateDoc3("ED-002_lid_A.SLDPRT",false,0,ref err);
   if(lid==null)lid=(IModelDoc2)sw.ActivateDoc3("ED-002_lid_A",false,0,ref err);
   log.WriteLine("LID_ACTIVATE "+err+" exists="+(lid!=null));
   try {
    object addin=sw.GetAddInObject("SldWorks.Simulation");
    ICosmosWorks cw=(ICosmosWorks)((ICwAddincallback)addin).CosmosWorks;
    log.WriteLine("SIMULATION_INTERFACE_OK");
    ICWModelDoc doc=(ICWModelDoc)cw.ActiveDoc;log.WriteLine("SIM_ACTIVE_DOC "+(doc!=null));
    ICWStudyManager mgr=(ICWStudyManager)doc.StudyManager;
    int code=0;ICWStudy study=(ICWStudy)mgr.CreateNewStudy3("Snap_static_A",0,0,out code);
    log.WriteLine("STUDY_CREATE code="+code+" exists="+(study!=null));
    if(study!=null) {
     ICWSolidManager solids=(ICWSolidManager)study.SolidManager;
     ICWSolidComponent comp=(ICWSolidComponent)solids.GetComponentAt(0,out code);
     ICWSolidBody body=(ICWSolidBody)comp.GetSolidBodyAt(0,out code);
     ICWMaterial mat=(ICWMaterial)body.GetDefaultMaterial();mat.MaterialUnits=0;mat.ModelType=0;mat.MaterialName="PETG assumed isotropic E2GPa";
     mat.SetPropertyByName("EX",2e9,0);mat.SetPropertyByName("NUXY",.38,0);mat.SetPropertyByName("DENS",1270,0);mat.SetPropertyByName("SIGYLD",35e6,0);
     log.WriteLine("MATERIAL code="+body.SetSolidBodyMaterial((CWMaterial)mat));
     object[] bs=(object[])((IPartDoc)lid).GetBodies2(0,false);object[] faces=(object[])((IBody2)bs[0]).GetFaces();
     IFace2 top=null,tip=null;
     foreach(IFace2 face in faces) {double[] b=(double[])face.GetBox();if(Math.Abs(b[2]-.0024)<1e-7 && Math.Abs(b[5]-.0024)<1e-7)top=face;
      if(Math.Abs(b[0]-.0373)<1e-7 && Math.Abs(b[3]-.0373)<1e-7)tip=face;}
     if(top==null||tip==null)throw new Exception("Boundary face selection failed");
     ICWLoadsAndRestraintsManager loads=(ICWLoadsAndRestraintsManager)study.LoadsAndRestraintsManager;
     var fixedFace=loads.AddRestraint(0,new object[]{top},null,out code);log.WriteLine("FIXTURE code="+code);
     ICWForce force=(ICWForce)loads.AddForce2(1,0,new object[]{tip},null,out code);log.WriteLine("FORCE code="+code);
     force.ForceBeginEdit();force.Unit=0;force.NormalForceOrTorqueValue=.805387;log.WriteLine("FORCE_EDIT code="+force.ForceEndEdit());
     ICWMesh mesh=(ICWMesh)study.Mesh;mesh.Quality=1;
     int meshCode=study.CreateMesh(0,1.2,.06);log.WriteLine("MESH code="+meshCode+" nodes="+mesh.NodeCount+" elements="+mesh.ElementCount);
     if(meshCode==0) {int solve=study.RunAnalysis();log.WriteLine("SOLVE code="+solve);
      if(solve==0){ICWResults results=(ICWResults)study.Results;
       log.WriteLine("STRESS_RAW "+string.Join(",",(object[])results.GetMinMaxStress(9,0,0,null,0,out code))+" code="+code);
       log.WriteLine("DISPLACEMENT_RAW "+string.Join(",",(object[])results.GetMinMaxDisplacement(3,0,null,0,out code))+" code="+code);}}
     lid.Save3(1,ref err,ref code);
    }
   }catch(Exception ex){log.WriteLine("SIMULATION_BLOCKED "+ex.GetType().Name+": "+ex.Message);}
  }
 }
 public static void ReadResults(string root) {
  ISldWorks sw=(ISldWorks)Marshal.GetActiveObject("SldWorks.Application");int e=0,w=0;
  IModelDoc2 lid=(IModelDoc2)sw.ActivateDoc3("ED-002_lid_A.SLDPRT",false,0,ref e);
  ICosmosWorks cw=(ICosmosWorks)((ICwAddincallback)sw.GetAddInObject("SldWorks.Simulation")).CosmosWorks;
  ICWStudyManager mgr=(ICWStudyManager)((ICWModelDoc)cw.ActiveDoc).StudyManager;
  ICWStudy study=(ICWStudy)mgr.GetStudy(mgr.ActiveStudy);
  using(var log=new StreamWriter(Path.Combine(root,"fea-results.txt"))) {
   ICWResults results=(ICWResults)study.Results;
   log.WriteLine("STRESS_VON_MISES_RAW_SI "+string.Join(",",(object[])results.GetMinMaxStress(9,0,0,null,0,out e))+" code="+e);
   log.WriteLine("DISPLACEMENT_RESULTANT_RAW_MM "+string.Join(",",(object[])results.GetMinMaxDisplacement(3,0,null,0,out e))+" code="+e);
   lid.Save3(1,ref e,ref w);log.WriteLine("STUDY_SAVE errors="+e+" warnings="+w);
  }
 }
}
