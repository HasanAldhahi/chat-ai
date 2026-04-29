
import { memo, useEffect, useState, useRef } from 'react'
import ModelSelectorSimple from "./ModelSelectorSimple";
import ModelSelectorExtended from "./ModelSelectorExtended";
import { useModal } from '../../modals/ModalContext';
import type { ModelInfo, ExtendedModelInfo } from '../../types/models';
import { isChatAiAgentModel } from "../../constants/chatAiAgentModels";
import { getDefaultConversation } from "../../utils/conversationUtils";

function ModelSelectorWrapper({modelsData, localState, setLocalState, inHeader = false}: {modelsData: [ModelInfo], localState: any, setLocalState: any, inHeader: boolean}) {
  /*
  render either ModelSelectorSimple or ModelSelectorExtended depending if modelsList contains models with extended==true
  */
  const { openModal } = useModal();
  
  const currentModelId = localState?.settings?.model?.id;
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  //const selectedModel = modelsData ? modelsData.find(model => model.id === currentModelId) || modelsData[0] || null : null;

  const hasExtendedModels =
    Array.isArray(modelsData) &&
    modelsData.length > 0 &&
    "description" in modelsData[0] &&
    (modelsData[0] as ExtendedModelInfo).description !== undefined;

  function setModel(newModel: ModelInfo) {
    if (newModel?.status === "offline") {
      openModal("serviceOffline");
    }
    setSelectedModel(newModel);
    setLocalState((prev) => {
      const wasAgent = isChatAiAgentModel(prev.settings?.model);
      const nowAgent = isChatAiAgentModel(newModel);
      const prevAgentId = prev.settings?.model?.id;
      const nextAgentId = newModel?.id;
      const switchingBetweenAgents =
        wasAgent && nowAgent && prevAgentId !== nextAgentId;
      const next = {
        ...prev,
        settings: {
          ...prev.settings,
          model: newModel,
        },
      };
      if (wasAgent !== nowAgent || switchingBetweenAgents) {
        const fresh = getDefaultConversation();
        return {
          ...next,
          messages: fresh.messages,
          messageCount: fresh.messageCount,
          lastModified: Date.now(),
        };
      }
      return next;
    });
  }

  // currentModelId has changed indirectly
  useEffect(() => {
    if(!currentModelId) return;
    if(modelsData.length === 0) return;

    const foundModel = modelsData.find(
      (model) => model.id === currentModelId
    );
    if (foundModel){
      setModel(foundModel);
    } else {
      // fallback to first model
      setModel(modelsData[0]);
    }
  }, [currentModelId, modelsData]);

  return (
    <>
      {
        hasExtendedModels ? 
          <ModelSelectorExtended selectedModel={selectedModel} modelsData={modelsData} inHeader={inHeader} onChange={setModel} /> 
        : 
          <ModelSelectorSimple selectedModel={selectedModel} modelsData={modelsData} inHeader={inHeader} onChange={setModel} />
      }
    </>
  )
}


export default memo(ModelSelectorWrapper);