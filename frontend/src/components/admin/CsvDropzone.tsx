import React, { RefObject } from "react";

interface CsvDropzoneProps {
  fileInputRef: RefObject<HTMLInputElement | null>;
  csvFile: File | null;
  importingCsv: boolean;
  importResult: any;
  importError: string;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onUploadCsv: () => void;
}

export const CsvDropzone: React.FC<CsvDropzoneProps> = ({
  fileInputRef,
  csvFile,
  importingCsv,
  importResult,
  importError,
  onFileChange,
  onUploadCsv,
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* CSV Import Dropzone */}
      <div className="md:col-span-2 bg-white border-2 border-dashed border-[#bdc8ce] hover:border-[#0891B2] rounded-2xl p-6 md:p-8 flex flex-col justify-center items-center text-center transition-colors relative group shadow-sm">
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          onChange={onFileChange}
          className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-10"
        />
        <span className="material-symbols-outlined text-4xl text-[#505f76] mb-2 group-hover:text-[#0891B2] transition-colors">
          upload_file
        </span>
        <h3 className="font-headline text-base font-bold text-[#191c1e] mb-1">
          {csvFile ? csvFile.name : "Drag and drop CSV files here"}
        </h3>
        <p className="font-body text-xs text-[#505f76] mb-4">
          {csvFile
            ? `${(csvFile.size / 1024).toFixed(1)} KB selected`
            : "or click anywhere to browse from your computer"}
        </p>

        <div className="flex items-center gap-3 z-20">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="bg-[#0891B2] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-4 py-2 rounded-full transition-colors cursor-pointer shadow-sm"
          >
            {csvFile ? "Change File" : "Select CSV File"}
          </button>
          {csvFile && (
            <button
              type="button"
              onClick={onUploadCsv}
              disabled={importingCsv}
              className="bg-[#00647c] hover:bg-[#007f9d] text-white font-label text-xs font-semibold px-4 py-2 rounded-full transition-colors flex items-center gap-1.5 shadow-sm cursor-pointer"
            >
              {importingCsv ? (
                <>
                  <span className="material-symbols-outlined text-xs animate-spin">progress_activity</span>
                  <span>Importing...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-xs">publish</span>
                  <span>Run Ingestion</span>
                </>
              )}
            </button>
          )}
        </div>

        {importResult && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-300 rounded-lg text-emerald-800 text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-sm text-emerald-600">check_circle</span>
            <span>
              Successfully imported {importResult.total_processed || importResult.imported || 0} policies!
            </span>
          </div>
        )}

        {importError && (
          <div className="mt-4 p-3 bg-[#ffdad6] border border-[#ba1a1a]/30 rounded-lg text-[#93000a] text-xs flex items-center gap-2">
            <span className="material-symbols-outlined text-sm text-[#ba1a1a]">error</span>
            <span>{importError}</span>
          </div>
        )}

        <div className="mt-4 pt-4 border-t border-[#e6e8ea] w-full flex justify-end">
          <a
            href="data:text/csv;charset=utf-8,policy_number,policy_type,coverage_amount,deductible,effective_date,expiry_date,policyholder_name,policyholder_dob,policyholder_phone%0APOL-8492-AX,motor,250000,1000,2023-01-01,2026-12-31,Sarah Jenkins,1990-05-15,5550192834%0APOL-3321-HM,home,400000,2000,2023-03-01,2027-03-01,Michael Chang,1985-08-20,5558471029"
            download="policy_template.csv"
            className="text-[#0891B2] hover:underline font-label text-xs flex items-center gap-1 z-20"
          >
            <span className="material-symbols-outlined text-[16px]">download</span>
            <span>Download Sample CSV Template</span>
          </a>
        </div>
      </div>

      {/* Ingestion Rules Card */}
      <div className="bg-white border border-[#e0e3e5] rounded-2xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4 pb-2 border-b border-[#f2f4f6]">
          <span className="material-symbols-outlined text-[#505f76]">rule</span>
          <h3 className="font-headline text-base font-bold text-[#191c1e]">Ingestion Rules</h3>
        </div>
        <ul className="space-y-4">
          <li className="flex items-start gap-2.5">
            <span className="material-symbols-outlined text-[#0891B2] text-[18px] mt-0.5">
              check_circle
            </span>
            <div>
              <h4 className="font-label text-xs font-semibold text-[#191c1e]">Data Validation</h4>
              <p className="font-body text-xs text-[#505f76] mt-0.5">
                Dates must follow standard YYYY-MM-DD format.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="material-symbols-outlined text-[#0891B2] text-[18px] mt-0.5">
              check_circle
            </span>
            <div>
              <h4 className="font-label text-xs font-semibold text-[#191c1e]">Required Fields</h4>
              <p className="font-body text-xs text-[#505f76] mt-0.5">
                Policy Number, Type, Coverage, and Holder DOB are mandatory.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-2.5">
            <span className="material-symbols-outlined text-[#ba1a1a] text-[18px] mt-0.5">
              error
            </span>
            <div>
              <h4 className="font-label text-xs font-semibold text-[#191c1e]">Duplicate Handling</h4>
              <p className="font-body text-xs text-[#505f76] mt-0.5">
                Existing Policy IDs will be updated in place with new parameters.
              </p>
            </div>
          </li>
        </ul>
      </div>
    </div>
  );
};
