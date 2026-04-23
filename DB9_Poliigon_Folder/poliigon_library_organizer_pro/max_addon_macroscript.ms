-- Poliigon Library Importer macroscript for 3ds Max (i8 BBBviz v2)
-- Place in: C:\Users\<user>\AppData\Local\Autodesk\3dsMax\<ver>\ENU\usermacros\
-- Or drag & drop this .ms into Max to install.
macroScript PoliigonLibImport
    category:"i8 Studio"
    toolTip:"Import Poliigon Library Folder (PBR -> VRayMtl/PhysMat)"
    buttonText:"Poliigon Import"
(
    fn findMaps folder = (
        local maps = #()
        if (getDirectories (folder + "/*")).count > 0 do (
            for sub in (getDirectories (folder + "/*")) do append maps sub
        )
        local files = #()
        local exts = #(".png",".jpg",".jpeg",".tif",".tiff",".exr")
        for f in (getFiles (folder + "/*.*")) do (
            for e in exts do (
                if (matchPattern f pattern:("*" + e)) do append files f
            )
        )
        -- also walk subfolders
        local subFolders = getDirectories (folder + "/*")
        for s in subFolders do (
            for f in (getFiles (s + "*.*")) do (
                for e in exts do (
                    if (matchPattern f pattern:("*" + e)) do append files f
                )
            )
        )
        return files
    )

    fn detectKey fname = (
        local lower = toLower fname
        if (findString lower "normal" != undefined or findString lower "_nrm" != undefined) then "NRM"
        else if (findString lower "rough" != undefined or findString lower "gloss" != undefined) then "ROUGH"
        else if (findString lower "metal" != undefined) then "METAL"
        else if (findString lower "disp" != undefined or findString lower "height" != undefined) then "DISP"
        else if (findString lower "_ao" != undefined or findString lower "ambient" != undefined) then "AO"
        else if (findString lower "alpha" != undefined or findString lower "opacity" != undefined) then "OPACITY"
        else if (findString lower "col" != undefined or findString lower "albedo" != undefined or findString lower "diff" != undefined) then "COL"
        else undefined
    )

    fn buildMat name maps = (
        local mat
        try ( mat = VRayMtl name:name ) catch ( mat = PhysicalMaterial name:name )
        for pair in maps do (
            local key = pair[1]
            local path = pair[2]
            local bmp = Bitmaptexture filename:path
            case key of (
                "COL":      (try (mat.texmap_diffuse = bmp) catch (mat.base_color_map = bmp))
                "NRM":      (try (mat.texmap_bump = bmp; mat.texmap_bump_multiplier = 100) catch ())
                "ROUGH":    (try (mat.texmap_reflectionGlossiness = bmp) catch (mat.roughness_map = bmp))
                "METAL":    (try (mat.texmap_metalness = bmp) catch (mat.metalness_map = bmp))
                "DISP":     (try (mat.texmap_displacement = bmp) catch ())
                "AO":       ( /* leave for compositor */ )
                "OPACITY":  (try (mat.texmap_opacity = bmp) catch ())
            )
        )
        return mat
    )

    on execute do (
        local folder = getSavePath caption:"Pick Poliigon asset folder"
        if folder == undefined then return false
        local files = findMaps folder
        if files.count == 0 then ( messageBox "No texture maps found." title:"Poliigon Importer"; return false )
        local buckets = #()
        for f in files do (
            local k = detectKey (filenameFromPath f)
            if k != undefined then append buckets #(k, f)
        )
        local name = filenameFromPath folder
        if name == "" do name = "Poliigon_Material"
        local mat = buildMat name buckets
        meditMaterials[1] = mat
        messageBox ("Created material: " + name + "\nMaps: " + (buckets.count as string)) title:"Poliigon Importer"
    )
)
