import { UploadForm } from "@/components/console/upload-dialog";
import { CampaignList } from "@/components/console/campaign-list";

export default function ConsolePage() {
  return (
    <div className="mx-auto max-w-4xl px-8 py-12">
      <h1 className="text-3xl font-bold tracking-tight text-foreground">
        Campaigns
      </h1>
      <p className="mt-2 text-sm text-muted">
        Upload base ads and generate localized variants.
      </p>
      <div className="mt-12 border-t border-border pt-8">
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
          New campaign
        </span>
        <div className="mt-4">
          <UploadForm />
        </div>
      </div>
      <div className="mt-16">
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted">
          All campaigns
        </span>
        <div className="mt-6">
          <CampaignList />
        </div>
      </div>
    </div>
  );
}
